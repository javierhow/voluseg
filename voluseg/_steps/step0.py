def process_parameters(parameters0=None):
    '''process parameters and create parameter file'''
    
    import os
    import copy
    import pickle
    import numpy as np
    from voluseg._tools.parameter_dictionary import parameter_dictionary
    
    parameters = copy.deepcopy(parameters0)
    
    ## general checks
    
    # check that parameter input is a dictionary
    if not type(parameters) == dict:
        print('error: specify parameter dictionary as input.')
        return
    
    # check if any parameters are missing
    missing_parameters = set(parameter_dictionary()) - set(parameters)    
    if missing_parameters:
        print('error: missing parameters %s.'%(', '.join(missing_parameters)))
        return
    
    # get input and output directories, and parameter filename
    dir_input = parameters['dir_input']
    dir_output = parameters['dir_output']
    filename_parameters = os.path.join(dir_output, 'parameters.pickle')
    
    # load parameters from file, if it already exists
    if os.path.isfile(filename_parameters):
        print('exiting, parameter file exists: %s.'%(filename_parameters))
        return
    
    ## specific checks
    
    # check directory names
    for i in ['dir_ants', 'dir_input', 'dir_output', 'registration']:
        pi = parameters[i]
        if not (isinstance(pi, str) and (not ' ' in pi)):
            print('error: parameter %s must be a string without spaces.'%(pi))
            return
    
    # check integers
    for i in ['ds', 'n_cells_block', 'n_colors', 'nt', 'planes_pad']:
        pi = parameters[i]
        if not (np.isscalar(pi) and (pi >= 0) and (pi == np.round(pi))):
            print('error: parameter %s must be a nonnegative or positive integer.'%(pi))
            return
    
    # check non-negative real numbers:
    for i in ['diam_cell', 'f_hipass', 'f_volume', 'res_x', 'res_y',
              'res_z', 't_baseline', 't_section', 'thr_mask']:
        pi = parameters[i]
        if not (np.isscalar(pi) and (pi >= 0) and np.isreal(pi)):
            print('error: parameter %s must be a nonnegative or positive real number.'%(pi))
            return
                       
    # check registration
    if parameters['registration']:
        parameters['registration'] = parameters['registration'].lower()
        if parameters['registration']=='none':
            parameters['registration'] = None
        elif not parameters['registration'] in ['high', 'medium', 'low']:
            print('error: \'registration\' must be either \'high\', \'medium\', \'low\', or \'none\'.')
            return
    
    # check plane padding
    if (not parameters['registration']) and not ((parameters['planes_pad'] == 0)):
            print('error: planes_pad must be 0 if registration is None.')
            return
        
    # get image extension, image names and number of segmentation timepoints
    file_names = [i.split('.', 1) for i in os.listdir(dir_input) if '.' in i]
    file_exts, counts = np.unique(list(zip(*file_names))[1], return_counts=True)
    ext = '.'+file_exts[np.argmax(counts)]
    volume_names = np.sort([i for i, j in file_names if '.'+j==ext])    
    lt = len(volume_names)
    
    # affine matrix
    affine_mat = np.diag([  parameters['res_x'] * parameters['ds'], \
                            parameters['res_y'] * parameters['ds'], \
                            parameters['res_z'], \
                            1])
    
    # save parameters    
    parameters['volume_names'] = volume_names
    parameters['ext'] = ext
    parameters['lt'] = lt
    parameters['affine_mat'] = affine_mat
        
    try:
        os.makedirs(dir_output, exist_ok=True)
        with open(filename_parameters, 'wb') as file_handle:
            pickle.dump(parameters, file_handle)        
            print('parameter file successfully saved.')
            
    except Exception as msg:
        print('parameter file not saved: %s.'%(msg))
                
