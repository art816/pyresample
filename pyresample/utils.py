#pyresample, Resampling of remote sensing image data in python
# 
#Copyright (C) 2010  Esben S. Nielsen
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Utility functions for pyresample"""

import numpy as np
from configobj import ConfigObj

import geometry, swath
import _spatial_mp

class AreaNotFound(Exception):
    """Exception raised when specified are is no found in file"""
    pass

def parse_area_file(area_file_name, *regions):
    """Parse area information from area file
    
    :Parameters:
    area_file : str
        Path to area definition file
    regions : str argument list 
        Regions to parse. If no regions are specified all 
        regions in the file are returned
             
    :Returns:
    area_defs : list
        List of AreaDefinition objects
        
    :Raises:
    AreaNotFound
        If a specified area is not found
    """
            
    area_file = open(area_file_name, 'r')
    area_list = list(regions)
    if len(area_list) == 0:
        select_all_areas = True
        area_defs = []
    else:
        select_all_areas = False
        area_defs = [None for i in area_list]
        
    #Extract area from file
    in_area = False
    for line in area_file.readlines():
        if not in_area:
            if 'REGION' in line:
                area_id = line.replace('REGION:', ''). \
                              replace('{', '').strip()
                if area_id in area_list or select_all_areas:
                    in_area = True
                    area_content = ''
        elif '};' in line:
            in_area = False            
            if select_all_areas:
                area_defs.append(_create_area(area_id, area_content))
            else:
                area_defs[area_list.index(area_id)] = _create_area(area_id,
                                                                   area_content)
        else:
            area_content += line

    area_file.close()
    
    #Check if all specified areas were found
    if not select_all_areas:
        for i, area in enumerate(area_defs):
            if area is None:
                raise AreaNotFound('Area "%s" not found in file "%s"'%
                                   (area_list[i], area_file_name))    
    return area_defs

def area_dict_to_area_def(area_dict):
    """Construct AreaDefinition object from dictionary
    
    :Parameters:
    area_dict : dict
        Dict containing areadefinition parameters. Dict keys are the ones
        used in area definition files
    
    :Returns: 
    area_def : object
        AreaDefinition object
    """
    
    return geometry.AreaDefinition(area_dict['PCS_ID'],
                                   area_dict['NAME'],
                                   area_dict['PCS_ID'],
                                   area_dict['PCS_DEF'],
                                   area_dict['XSIZE'],
                                   area_dict['YSIZE'],
                                   area_dict['AREA_EXTENT'])

def _create_area(area_id, area_content):
    """Parse area configuration"""
    
    config_obj = ConfigObj(area_content.replace(':', '=').replace('{', ''). 
                           replace('};', '').splitlines())

    config = config_obj.dict()
    config['REGION'] = area_id
    try:
        config['NAME'].__iter__()
        config['NAME'] = ', '.join(config['NAME'])
    except:
        config['NAME'] = ''.join(config['NAME'])
    config['XSIZE'] = int(config['XSIZE'])
    config['YSIZE'] = int(config['YSIZE'])
    config['AREA_EXTENT'][0] = config['AREA_EXTENT'][0].replace('(', '')
    config['AREA_EXTENT'][3] = config['AREA_EXTENT'][3].replace(')', '')
    
    for i, val in enumerate(config['AREA_EXTENT']):
        config['AREA_EXTENT'][i] = float(val)
        
    config['PCS_DEF'] = _get_proj4_args(config['PCS_DEF'])
    
    return geometry.AreaDefinition(config['REGION'], config['NAME'], 
                                   config['PCS_ID'], config['PCS_DEF'], 
                                   config['XSIZE'], config['YSIZE'], 
                                   config['AREA_EXTENT'])

def get_area_def(area_id, area_name, proj_id, proj4_args, x_size, y_size,
                 area_extent):
    """Construct AreaDefinition object from arguments
    
    :Parameters:
    area_id : str
        ID of area
    proj_id : str
        ID of projection
    area_name :str
        Description of area
    proj4_args : list or str
        Proj4 arguments as list of arguments or string
    x_size : int
        Number of pixel in x dimension
    y_size : int  
        Number of pixel in y dimension
    area_extent : list 
        Area extent as a list of ints (LL_x, LL_y, UR_x, UR_y)
    
    :Returns: 
    area_def : object
        AreaDefinition object
    """
    
    proj_dict = _get_proj4_args(proj4_args)
    return geometry.AreaDefinition(area_id, area_name, proj_id, proj_dict, x_size,
                               y_size, area_extent)
  
def generate_cartesian_grid(area_def, nprocs=1):
    """Generate the cartesian coordinates grid of the area
    
    :Parameters:
    area_def : object
        Area definition as AreaDefinition object
    nprocs : int, optional 
        Number of processor cores to be used
    
    :Returns: 
    grid : numpy array
        Cartesian grid
    """
    
    if nprocs > 1:
        cartesian = _spatial_mp.Cartesian_MP(nprocs)
    else:
        cartesian = _spatial_mp.Cartesian()
     
    grid_lons, grid_lats = area_def.get_lonlats(nprocs)
    
    shape = list(grid_lons.shape)
    shape.append(3)
    cart_coords = cartesian.transform_latlons(grid_lons.ravel(),
                                              grid_lats.ravel())
    return cart_coords.reshape(shape)
    

def generate_quick_linesample_arrays(source_area_def, target_area_def, nprocs=1):
    """Generate linesample arrays for quick grid resampling
    
    :Parameters:
    source_area_def : object 
        Source area definition as AreaDefinition object
    target_area_def : object 
        Target area definition as AreaDefinition object
    nprocs : int, optional 
        Number of processor cores to be used

    :Returns: 
    (row_indices, col_indices) : list of numpy arrays
    """
        
    lons, lats = target_area_def.get_lonlats(nprocs)
    
    #Proj.4 definition of source area projection
    if nprocs > 1:
        source_proj = _spatial_mp.Proj_MP(**source_area_def.proj_dict)
    else:
        source_proj = _spatial_mp.Proj(**source_area_def.proj_dict)

    #Get cartesian projection values from longitude and latitude 
    source_x, source_y = source_proj(lons, lats, nprocs=nprocs)

    #Free memory
    del(lons)
    del(lats)
    
    #Find corresponding pixels (element by element conversion of ndarrays)
    source_pixel_x = (source_x/source_area_def.pixel_size_x + \
                      source_area_def.pixel_offset_x).astype('int')
    
    source_pixel_y = (source_area_def.pixel_offset_y - \
                     source_y/source_area_def.pixel_size_y).astype('int')
                     
    return source_pixel_y, source_pixel_x

def generate_nearest_neighbour_linesample_arrays(source_area_def, target_area_def, 
                                                 radius_of_influence, nprocs=1):
    """Generate linesample arrays for nearest neighbour grid resampling
    
    :Parameters:
    source_area_def : object 
        Source area definition as AreaDefinition object
    target_area_def : object 
        Target area definition as AreaDefinition object
    radius_of_influence : float 
        Cut off distance in meters
    nprocs : int, optional 
        Number of processor cores to be used

    :Returns: 
    (row_indices, col_indices) : list of numpy arrays
    """
    
    lons, lats = source_area_def.get_lonlats(nprocs)
    
    valid_index, index_array, distance_array = \
                                swath.get_neighbour_info(lons.ravel(), 
                                                         lats.ravel(), 
                                                         target_area_def, 
                                                         radius_of_influence, 
                                                         neighbours=1,
                                                         nprocs=nprocs)
    #Enumerate rows and cols
    rows = np.fromfunction(lambda i, j: i, source_area_def.shape, 
                           dtype=np.int).ravel()
    cols = np.fromfunction(lambda i, j: j, source_area_def.shape, 
                           dtype=np.int).ravel()
    
    #Reduce to match resampling data set
    rows_valid = rows[valid_index]
    cols_valid = cols[valid_index]
    
    #Get result using array indexing
    number_of_valid_points = valid_index.sum()
    index_mask = (index_array == number_of_valid_points)
    index_array[index_mask] = 0
    row_sample = rows_valid[index_array]
    col_sample = cols_valid[index_array]
    row_sample[index_mask] = -1
    col_sample[index_mask] = -1
    
    #Reshape to correct shape
    row_indices = row_sample.reshape(target_area_def.shape)
    col_indices = col_sample.reshape(target_area_def.shape)
    
    return row_indices, col_indices
    
def _get_proj4_args(proj4_args):
    """Create dict from proj4 args"""
    
    if isinstance(proj4_args, str):
        proj_config = ConfigObj(proj4_args.replace('+', '').split())
    else:
        proj_config = ConfigObj(proj4_args)
    return proj_config.dict()