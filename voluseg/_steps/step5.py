def clean_cells(parameters):
    '''remove noise cells, detrend and detect baseline'''
    
    import os
    import h5py
    import shutil
    import numpy as np
    from types import SimpleNamespace
    from itertools import combinations
    from pyspark.sql.session import SparkSession
    from voluseg._tools.clean_signal import clean_signal

    spark = SparkSession.builder.getOrCreate()
    sc = spark.sparkContext
    p = SimpleNamespace(**parameters)
    
    thr_similarity = 0.5
    
    for color_i in range(p.n_colors):
        if os.path.isfile(os.path.join(p.dir_output, 'cells%d_clean.hdf5'%(color_i))):
            continue
                
        with h5py.File(os.path.join(p.dir_output, 'cells%d_raw.hdf5'%(color_i)), 'r') as file_handle:
            cell_xyz = file_handle['cell_xyz'][()]
            cell_weights = file_handle['cell_weights'][()]
            cell_timeseries = file_handle['cell_timeseries'][()]
            cell_lengths = file_handle['cell_lengths'][()]
            x, y, z, t = file_handle['dimensions'][()]
            
        with h5py.File(os.path.join(p.dir_output, 'volume%d.hdf5'%(color_i)), 'r') as file_handle:
            volume_mask = file_handle['volume_mask'][()].T
            
        cell_x = cell_xyz[:, :, 0]
        cell_y = cell_xyz[:, :, 1]
        cell_z = cell_xyz[:, :, 2]
        cell_w = np.nansum(cell_weights, 1)
                
        ix = np.any(np.isnan(cell_timeseries), 1);
        if np.any(ix):
            print('nans (to be removed): %d' %np.count_nonzero(ix))
            cell_timeseries[ix] = 0
            
        cell_valids = np.zeros(len(cell_w), dtype=bool);
        for i, (li, xi, yi, zi) in enumerate(zip(cell_lengths, cell_x, cell_y, cell_z)):
            cell_valids[i] = np.mean(volume_mask[xi[:li], yi[:li], zi[:li]]) > p.thr_mask
            
        # brain mask array
        volume_list = [[[[] for zi in range(z)] for yi in range(y)] for xi in range(x)]
        volume_cell_n = np.zeros((x, y, z), dtype='int')
        for i, (li, vi) in enumerate(zip(cell_lengths, cell_valids)):
            for j in range(li if vi else 0):
                xij, yij, zij = cell_x[i, j], cell_y[i, j], cell_z[i, j]
                volume_list[xij][yij][zij].append(i)
                volume_cell_n[xij, yij, zij] += 1
                    
        pair_cells = [pi for a in volume_list for b in a for c in b for pi in combinations(c, 2)]
        assert(len(pair_cells) == np.sum(volume_cell_n * (volume_cell_n - 1) / 2))
        
        # remove duplicate cells
        pair_id, pair_count = np.unique(pair_cells, axis=0, return_counts=True)
        for pi, fi in zip(pair_id, pair_count):
            pair_overlap = (fi / np.mean(cell_lengths[pi])) > thr_similarity
            pair_correlation = np.corrcoef(cell_timeseries[pi])[0, 1] > thr_similarity
            if (pair_overlap and pair_correlation):
                cell_valids[pi[np.argmin(cell_w[pi])]] = 0
        
        ## get valid version of cells ##
        cell_weights = cell_weights[cell_valids]
        cell_timeseries = cell_timeseries[cell_valids] 
        cell_lengths = cell_lengths[cell_valids]
        cell_x = cell_x[cell_valids]
        cell_y = cell_y[cell_valids]
        cell_z = cell_z[cell_valids]
        cell_w = cell_w[cell_valids]
        ## end get valid version of cells ##
        
        bparameters = sc.broadcast(parameters)
        get_timebase = lambda timeseries: clean_signal(bparameters.value, timeseries)
        try:
            timebase = sc.parallelize(cell_timeseries).map(get_timebase).collect()
        except:
            print('failed parallel baseline computation, proceeding serially.')
            timebase = list(zip(*map(get_timebase, cell_timeseries)))
        
        cell_timeseries1, cell_baseline1 = list(zip(*timebase))
        
        n = np.count_nonzero(cell_valids)
        volume_id = -1 + np.zeros((x, y, z))
        volume_weight = np.zeros((x, y, z))
        for i, li in enumerate(cell_lengths):
            for j in range(li):
                xij, yij, zij = cell_x[i, j], cell_y[i, j], cell_z[i, j]
                if cell_weights[i, j] > volume_weight[xij, yij, zij]:
                    volume_id[xij, yij, zij] = i;
                    volume_weight[xij, yij, zij] = cell_weights[i, j]
                    
        with h5py.File(os.path.join(p.dir_output, 'volume%s.hdf5'%(color_i)), 'r') as file_handle:
            background = file_handle['background'][()]
                    
        with h5py.File(os.path.join(p.dir_output, 'cells%d_clean.hdf5'%(color_i)), 'w') as file_handle:
            file_handle['n'] = n
            file_handle['t'] = t
            file_handle['x'] = x
            file_handle['y'] = y
            file_handle['z'] = z
            file_handle['cell_x'] = cell_x
            file_handle['cell_y'] = cell_y
            file_handle['cell_z'] = cell_z
            file_handle['volume_id'] = volume_id
            file_handle['volume_weight'] = volume_weight
            file_handle['cell_weights'] = cell_weights.astype('float32')
            file_handle['cell_timeseries_raw'] = cell_timeseries.astype('float32')
            file_handle['cell_timeseries'] = np.array(cell_timeseries1).astype('float32')
            file_handle['cell_baseline'] = np.array(cell_baseline1).astype('float32')
            file_handle['background'] = background

    # clean up
    completion = 1
    for color_i in range(p.n_colors):        
        if not os.path.isfile(os.path.join(p.dir_output, 'cells%s_clean.hdf5'%(color_i))):
            completion= 0
            
    if completion:
        shutil.rmtree(os.path.join(p.dir_output, 'volumes'))
        shutil.rmtree(os.path.join(p.dir_output, 'cells'))