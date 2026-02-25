% =========================================================================
% LABCHART TO MAT EXPORT SCRIPT
% =========================================================================
%
% Exports LabChart .adicht files to .mat format for the Python RHC pipeline.
%
% REQUIREMENTS:
%   - Windows (recommended for best SDK compatibility)
%   - ADInstruments SDK (adi package added to path)
%
% USAGE:
%   1. Run this script in MATLAB (or call export_to_mat() from the command window)
%   2. Select the input directory containing .adicht files when prompted
%   3. Select the output directory for .mat exports when prompted
%   4. Transfer the .mat files (and original .adicht files)
%   5. Run the Python pipeline: python scripts/run_pipeline.py ...
%
%   Alternatively, call with arguments to skip the dialogs:
%     export_to_mat('C:\path\to\adicht_files', 'C:\path\to\mat_output')
%
% OUTPUT FORMAT:
%   The .mat file contains:
%   - data: [n_samples x n_channels] waveform matrix
%   - titles: cell array of channel names
%   - tickrate: sample rate in Hz
%   - datastart: start indices for each record block
%   - dataend: end indices for each record block
%   - blocktimes: start times for each block (datenum format)
%
% =========================================================================

function export_to_mat(input_dir, output_dir)
% EXPORT_TO_MAT Exports LabChart .adicht files to .mat format
%
% Usage:
%   export_to_mat()                     % Prompts for directories
%   export_to_mat(input_dir, output_dir) % Uses provided directories

%% CONFIGURATION
config = struct();
config.channels_to_extract = {'ECG', 'Pressure'};  % Channels to include
config.concatenate_records = true;  % Combine multi-record files into single array
config.fill_gaps_with_nan = true;   % Fill gaps between records with NaN

%% ARGUMENT HANDLING
if nargin < 1 || isempty(input_dir)
    input_dir = uigetdir(pwd, 'Select Input Directory (.adicht files)');
    if input_dir == 0, return; end 
end

if nargin < 2 || isempty(output_dir)
    output_dir = uigetdir(input_dir, 'Select Output Directory (for .mat files)');
    if output_dir == 0, return; end
end

config.input_dir = input_dir;
config.output_dir = output_dir;

%% INITIALIZATION
if ~exist(config.output_dir, 'dir')
    mkdir(config.output_dir);
end

file_list = dir(fullfile(config.input_dir, '*.adicht'));
fprintf('========================================\n');
fprintf('LABCHART TO MAT EXPORT\n');
fprintf('========================================\n');
fprintf('Input:  %s\n', config.input_dir);
fprintf('Output: %s\n', config.output_dir);
fprintf('Found %d .adicht files\n\n', length(file_list));

%% MAIN PROCESSING LOOP
successful = 0;
failed = 0;

for i = 1:length(file_list)
    try
        input_file = fullfile(config.input_dir, file_list(i).name);
        [~, basename, ~] = fileparts(file_list(i).name);
        output_file = fullfile(config.output_dir, [basename '.mat']);
        
        fprintf('[%d/%d] %s... ', i, length(file_list), file_list(i).name);
        
        % Read LabChart file
        lc_data = adi.readFile(input_file);
        
        % Find channels
        [channel_names, channel_indices] = find_channels(lc_data.channel_names, config.channels_to_extract);
        
        % Get sample rate from first record (assume consistent)
        sample_rate = lc_data.records(1).tick_fs;
        
        % Export based on record structure
        if lc_data.n_records == 1
            % Single record - simple export
            export_data = export_single_record(lc_data, channel_indices);
        else
            % Multi-record - concatenate with gap handling
            export_data = export_multi_record(lc_data, channel_indices, config);
        end
        
        % Add channel names and sample rate
        export_data.titles = channel_names;
        export_data.tickrate = sample_rate;
        
        % Save .mat file
        save(output_file, '-struct', 'export_data', '-v7.3');
        
        fprintf('OK (%d samples, %.0f Hz)\n', size(export_data.data, 1), export_data.tickrate);
        successful = successful + 1;
        
    catch ME
        fprintf('FAILED: %s\n', ME.message);
        failed = failed + 1;
    end
end

%% SUMMARY
fprintf('\n========================================\n');
fprintf('EXPORT COMPLETE\n');
fprintf('  Successful: %d\n', successful);
fprintf('  Failed:     %d\n', failed);
fprintf('  Output dir: %s\n', config.output_dir);
fprintf('========================================\n');
end

% =========================================================================
% HELPER FUNCTIONS
% =========================================================================

function [channel_names, channel_indices] = find_channels(available_channels, required_channels)
    % Find required channels in available channel list (case-insensitive)
    
    channel_names = {};
    channel_indices = [];
    
    available_upper = upper(available_channels);
    
    for i = 1:length(required_channels)
        target = upper(required_channels{i});
        idx = find(strcmp(available_upper, target), 1);
        
        if isempty(idx)
            error('Channel "%s" not found. Available: %s', ...
                required_channels{i}, strjoin(available_channels, ', '));
        end
        
        channel_names{end+1} = required_channels{i};  % Use standard name
        channel_indices(end+1) = idx;
    end
end

function export_data = export_single_record(lc_data, channel_indices)
    % Export a single-record file
    
    record = lc_data.records(1);
    n_samples = record.n_ticks;
    n_channels = length(channel_indices);
    
    data = zeros(n_samples, n_channels);
    
    for i = 1:n_channels
        ch_idx = channel_indices(i);
        % Use channel_specs to get data
        ch_spec = lc_data.channel_specs(ch_idx);
        ch_data = ch_spec.getData(1);
        
        % Handle potential length mismatch (though rare in single record)
        actual_len = min(length(ch_data), n_samples);
        data(1:actual_len, i) = ch_data(1:actual_len);
    end
    
    export_data.data = data;
    export_data.datastart = 1;
    export_data.dataend = n_samples;
    % Convert datetime to datenum if needed, or keeping it simple
    if isprop(record, 'record_start_datetime')
         export_data.blocktimes = datenum(record.record_start_datetime);
    else
         export_data.blocktimes = 0; % Fallback
    end
end

function export_data = export_multi_record(lc_data, channel_indices, config)
    % Export a multi-record file, concatenating records
    
    n_records = lc_data.n_records;
    n_channels = length(channel_indices);
    sample_rate = lc_data.records(1).tick_fs;
    
    % Calculate total size needed (including gaps)
    total_samples = 0;
    record_info = struct('start_idx', {}, 'n_samples', {}, 'start_time', {}, 'end_time', {});
    
    for r = 1:n_records
        rec = lc_data.records(r);
        n_samples = rec.n_ticks;
        start_time = rec.record_start_datetime;
        duration = rec.duration; % Duration in seconds usually? Or check property
        % Typically rec.duration is seconds
        end_time = start_time + seconds(duration);
        
        % Calculate gap before this record (if not first)
        if r > 1 && config.fill_gaps_with_nan
            prev_end = record_info(r-1).end_time;
            gap_seconds = seconds(start_time - prev_end);
            
            % If gap is negative (overlap), clamp to 0
            if gap_seconds < 0
                gap_seconds = 0;
            end
            
            gap_samples = round(gap_seconds * sample_rate);
            total_samples = total_samples + gap_samples;
        end
        
        record_info(r).start_idx = total_samples + 1;
        record_info(r).n_samples = n_samples;
        record_info(r).start_time = start_time;
        record_info(r).end_time = end_time;
        
        total_samples = total_samples + n_samples;
    end
    
    % Pre-allocate with NaN (for gaps)
    data = nan(total_samples, n_channels);
    
    % Fill in each record
    datastart = zeros(1, n_records);
    dataend = zeros(1, n_records);
    blocktimes = zeros(1, n_records);
    
    for r = 1:n_records
        start_idx = record_info(r).start_idx;
        n_samples = record_info(r).n_samples;
        end_idx = start_idx + n_samples - 1;
        
        for i = 1:n_channels
            ch_idx = channel_indices(i);
            % Use channel_specs to get data
            ch_spec = lc_data.channel_specs(ch_idx);
            ch_data = ch_spec.getData(r);
            
            actual_len = min(length(ch_data), n_samples);
            data(start_idx:(start_idx+actual_len-1), i) = ch_data(1:actual_len);
        end
        
        datastart(r) = start_idx;
        dataend(r) = end_idx;
        blocktimes(r) = datenum(record_info(r).start_time);
    end
    
    export_data.data = data;
    export_data.datastart = datastart;
    export_data.dataend = dataend;
    export_data.blocktimes = blocktimes;
end
