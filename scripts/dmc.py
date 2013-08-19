#! /usr/bin/env python

"""
Main CLI for PyMsBayes package.
"""

import os
import sys
import re
import glob
import multiprocessing
import random
import argparse
import datetime
import logging

from pymsbayes.fileio import expand_path, process_file_arg, open
from pymsbayes.utils import GLOBAL_RNG, set_memory_trace, MSBAYES_SORT_INDEX
from pymsbayes.utils.messaging import get_logger, LOGGING_LEVEL_ENV_VAR
from pymsbayes.utils.parsing import line_count
from pymsbayes.config import MsBayesConfig
from pymsbayes.utils.functions import (is_file, is_dir, long_division,
        mk_new_dir)

_LOG = get_logger(__name__)

_program_info = {
    'name': os.path.basename(__file__),
    'author': 'Jamie Oaks',
    'version': 'Version 0.1.0',
    'description': __doc__,
    'copyright': 'Copyright (C) 2013 Jamie Oaks',
    'license': 'GNU GPL version 3 or later',}

class InfoLogger(object):
    def __init__(self, path):
        self.path = path

    def write(self, msg, log_func=None):
        out = open(self.path, 'a')
        out.write(msg)
        out.close()
        if log_func:
            log_func(msg)

def arg_is_path(path):
    try:
        if not os.path.exists(path):
            raise
    except:
        msg = 'path {0!r} does not exist'.format(path)
        raise argparse.ArgumentTypeError(msg)
    return expand_path(path)

def arg_is_file(path):
    try:
        if not is_file(path):
            raise
    except:
        msg = '{0!r} is not a file'.format(path)
        raise argparse.ArgumentTypeError(msg)
    return expand_path(path)

def arg_is_config(path):
    try:
        if not MsBayesConfig.is_config(path):
            raise
    except:
        msg = '{0!r} is not an msBayes config file'.format(path)
        raise argparse.ArgumentTypeError(msg)
    return expand_path(path)

def arg_is_dir(path):
    try:
        if not is_dir(path):
            raise
    except:
        msg = '{0!r} is not a directory'.format(path)
        raise argparse.ArgumentTypeError(msg)
    return expand_path(path)

def main_cli():
    description = '{name} {version}'.format(**_program_info)
    parser = argparse.ArgumentParser(description = description)
    parser.add_argument('-o', '--observed-configs',
            nargs = '+',
            type = arg_is_config,
            required = True,
            help = ('One or more msBayes config files to be used to either '
                    'calculate or simulate observed summary statistics. If '
                    'used in combination with `-r` each config will be used to '
                    'simulate pseudo-observed data. If analyzing real data, do '
                    'not use the `-r` option, and the fasta files specified '
                    'within the config must exist and contain the sequence '
                    'data.'))
    parser.add_argument('-p', '--prior-configs',
            nargs = '+',
            type = arg_is_path,
            required = True,
            help = ('One or more config files to be used to generate prior '
                    'samples. If more than one config is specified, they '
                    'should be separated by spaces. '
                    'This option can also be used to specify the path to a '
                    'directory containing the prior samples and summary '
                    'statistic means and standard deviations generated by a '
                    'previous run using the `generate-samples-only` option. '
                    'These files should be found in the directory '
                    '`pymsbayes-output/prior-stats-summaries`. If specifying '
                    'this directory, it should be the only argument (i.e., '
                    'no other directories or config files can be provided).'))
    parser.add_argument('-r', '--reps',
            action = 'store',
            type = int,
            default = 0,
            help = ('This option has two effects. First, it signifies that '
                    'the analysis will be simulation based (i.e., no real '
                    'data will be used). Second, it specifies how many '
                    'simulation replicates to perform (i.e., how many data '
                    'sets to simulate and analyze).'))
    parser.add_argument('-n', '--num-prior-samples',
            action = 'store',
            type = int,
            default = 1000000,
            help = ('The number of prior samples to simulate for each prior '
                    'config specified with `-p`.'))
    parser.add_argument('--prior-batch-size',
            action = 'store',
            type = int,
            default = 10000,
            help = ('The number of prior samples to simulate for each batch.'))
    parser.add_argument('--generate-samples-only',
            action = 'store_true',
            help = ('Only generate samples from models as requested. I.e., '
                    'No analyses are performed to approximate posteriors. '
                    'This option can be useful if you want the prior samples '
                    'for other purposes.'))
    parser.add_argument('--num-posterior-samples',
            action = 'store',
            type = int,
            default = 1000,
            help = ('The number of posterior samples desired for each '
                    'analysis. Default: 1000.'))
    parser.add_argument('--num-standardizing-samples',
            action = 'store',
            type = int,
            default = 10000,
            help = ('The number of prior samples desired to use for '
                    'standardizing statistics. Default: 10000.'))
    parser.add_argument('--np',
            action = 'store',
            type = int,
            default = multiprocessing.cpu_count(),
            help = ('The maximum number of processes to run in parallel. The '
                    'default is the number of CPUs available on the machine.'))
    parser.add_argument('--output-dir',
            action = 'store',
            type = arg_is_dir,
            help = ('The directory in which all output files will be written. '
                    'The default is to use the directory of the first observed '
                    'config file.'))
    parser.add_argument('--temp-dir',
            action = 'store',
            type = arg_is_dir,
            help = ('A directory to temporarily stage files. The default is to '
                    'use the output directory.'))
    parser.add_argument('--staging-dir',
            action = 'store',
            type = arg_is_dir,
            help = ('A directory to temporarily stage prior files. This option '
                    'can be useful on clusters to speed up I/O while '
                    'generating prior samples. You can designate a local temp '
                    'directory on a compute node to avoid constant writing to '
                    'a shared drive. The default is to use the `temp-dir`.'))
    parser.add_argument('-s', '--stat-prefixes',
            nargs = '*',
            type = str,
            help = ('Prefixes of summary statistics to use in the analyses. '
                    'The prefixes should be separated by spaces. '
                    'Default: `-s pi wattTheta pi.net tajD.denom`.'))
    parser.add_argument('-b', '--bandwidth',
            action = 'store',
            type = float,
            help = ('Smoothing parameter for the posterior kernal density '
                    'estimation. This option is used for the `glm` '
                    'regression method. The default is 2 / '
                    '`num-posterior-samples`.'))
    parser.add_argument('-q', '--num-posterior-quantiles',
            action = 'store',
            type = int,
            default = 1000,
            help = ('The number of equally spaced quantiles at which to '
                    'evaluate the GLM-estimated posterior density. '
                    'Default: 1000.'))
    parser.add_argument('--reporting-frequency',
            action = 'store',
            type = int,
            default = 0,
            help = ('How frequently (in batch iterations) to run regression '
                    'and report current results. '
                    'Default: 0 (only report final results).'))
    parser.add_argument('--sort-index',
            action = 'store',
            type = int,
            default = 7,
            choices = range(8),
            help = ('The sorting index used by `msbayes.pl` and '
                    '`obsSumStats.pl` scripts to determine how the summary '
                    'statistics of the taxon pairs are to be re-sorted for the'
                    'observed and simulated data. The default (7) sorts by pi '
                    'between populations of each taxon pair. Specifying "0" '
                    'prevent sorting and retain information regarding '
                    'taxon-pair identity. All other options (1-7) throw out '
                    'information specific to taxon-pair identity.'))
    parser.add_argument('--no-global-estimate',
            action = 'store_true',
            help = ('If multiple prior models are specified, by default a '
                    'global estimate is performed averaging over all models. '
                    'This option prevents the global estimation (i.e., only '
                    'inferences for each model are made).'))
    parser.add_argument('--compress',
            action = 'store_true',
            help = 'Compress large results files.')
    parser.add_argument('--keep-temps',
            action = 'store_true',
            help = 'Keep all temporary files.')
    parser.add_argument('--seed',
            action = 'store',
            type = int,
            help = 'Random number seed to use for the analysis.')
    parser.add_argument('--output-prefix',
            action = 'store',
            type = str,
            default = '',
            help = ('Prefix to use at beginning of output files. The default '
                    'is no prefix.'))
    parser.add_argument('--version',
            action = 'version',
            version = '%(prog)s ' + _program_info['version'],
            help = 'Report version and exit.')
    parser.add_argument('--quiet',
            action = 'store_true',
            help = 'Run with verbose messaging.')
    parser.add_argument('--debug',
            action = 'store_true',
            help = 'Run in debugging mode.')

    args = parser.parse_args()

    ##########################################################################
    ## handle args

    MSBAYES_SORT_INDEX.set_index(args.sort_index)

    _LOG.setLevel(logging.INFO)
    os.environ[LOGGING_LEVEL_ENV_VAR] = "INFO"
    if args.quiet:
        _LOG.setLevel(logging.WARNING)
        os.environ[LOGGING_LEVEL_ENV_VAR] = "WARNING"
    if args.debug:
        _LOG.setLevel(logging.DEBUG)
        os.environ[LOGGING_LEVEL_ENV_VAR] = "DEBUG"

    from pymsbayes.workers import (MsBayesWorker, merge_prior_files,
            ObsSumStatsWorker)
    from pymsbayes.teams import ABCTeam
    from pymsbayes.utils.parsing import (get_patterns_from_prefixes,
        DEFAULT_STAT_PATTERNS, DIV_MODEL_PATTERNS, MODEL_PATTERNS, PSI_PATTERNS,
        MEAN_TAU_PATTERNS, OMEGA_PATTERNS)
    from pymsbayes.manager import Manager
    from pymsbayes.utils.tempfs import TempFileSystem

    if len(args.observed_configs) != len(set(args.observed_configs)):
        raise ValueError('All paths to observed config files must be unique')

    # vet prior-configs option
    using_previous_priors = False
    previous_prior_dir = None
    if (len(args.prior_configs) == 1) and (is_dir(args.prior_configs[0])):
        previous_prior_dir = args.prior_configs.pop(0)
        previous_priors = glob.glob(os.path.join(previous_prior_dir,
                '*-prior-sample.txt'))
        previous_sums = glob.glob(os.path.join(previous_prior_dir,
                '*-means-and-std-devs.txt'))
        if (not previous_priors) or (not previous_sums):
            raise ValueError('directory {0!r} specified with `prior-configs` '
                    'option does not contain necessary prior and summary '
                    'files'.format(args.prior_configs[0]))
        using_previous_priors = True
    else:
        for path in args.prior_configs:
            if not is_file(path):
                raise ValueError('prior config {0!r} is not a file'.format(
                        path))
    if len(args.prior_configs) != len(set(args.prior_configs)):
        raise ValueError('All paths to prior config files must be unique') 
    if not args.output_dir:
        args.output_dir = os.path.dirname(args.observed_configs[0])
    base_dir = mk_new_dir(os.path.join(args.output_dir, 'pymsbayes-results'))
    if not args.temp_dir:
        args.temp_dir = base_dir
    info = InfoLogger(os.path.join(base_dir, args.output_prefix + \
            'pymsbayes-info.txt'))
    info.write('[pymsbayes]\n'.format(base_dir))
    info.write('\tversion = {version}\n'.format(**_program_info))
    info.write('\toutput_directory = {0}\n'.format(base_dir))
    temp_fs = TempFileSystem(parent=args.temp_dir, prefix='temp-files-')
    base_temp_dir = temp_fs.base_dir
    info.write('\ttemp_directory = {0}\n'.format(base_temp_dir))
    info.write('\tsort_index = {0}\n'.format(
            MSBAYES_SORT_INDEX.current_value()))
    if (args.reps < 1):
        info.write('\tsimulate_data = False\n')
    else:
        info.write('\tsimulate_data = True\n')
    stat_patterns = DEFAULT_STAT_PATTERNS
    if args.stat_prefixes:
        for i in range(len(args.stat_prefixes)):
            if not args.stat_prefixes[i].endswith('.'):
                args.stat_prefixes[i] += '.'
        stat_patterns = get_patterns_from_prefixes(
                args.stat_prefixes,
                ignore_case=True)
    if not args.bandwidth:
        args.bandwidth = 2 / float(args.num_posterior_samples)
    if not args.seed:
        args.seed = random.randint(1, 999999999)
    GLOBAL_RNG.seed(args.seed)
    observed_dir = mk_new_dir(os.path.join(base_dir, 'observed-summary-stats'))
    observed_paths = [os.path.join(observed_dir, args.output_prefix + \
            'observed-{0}.txt'.format(i+1)) for i in range(len(
                    args.observed_configs))]
    info.write('\tseed = {0}\n'.format(args.seed))
    info.write('\tnum_processors = {0}\n'.format(args.np))
    info.write('\tbandwidth = {0}\n'.format(args.bandwidth))
    info.write('\tposterior_quantiles = {0}\n'.format(
            args.num_posterior_quantiles))
    info.write('\tposterior_sample_size = {0}\n'.format(
            args.num_posterior_samples))
    info.write('\tnum_standardizing_samples = {0}\n'.format(
            args.num_posterior_samples))
    info.write('\t\tstat_patterns = {0}\n'.format(
            ', '.join([p.pattern for p in stat_patterns])))
    info.write('\t[[observed_configs]]\n')
    for i, cfg in enumerate(args.observed_configs):
        info.write('\t\t{0} = {1}\n'.format(i + 1, cfg))
    info.write('\t[[observed_paths]]\n')
    for i, p in enumerate(observed_paths):
        info.write('\t\t{0} = {1}\n'.format(i + 1, p))

    models_to_configs = {}
    configs_to_models = {}
    num_taxon_pairs = None
    for i in range(len(args.prior_configs)):
        model_idx = i + 1
        models_to_configs[model_idx] = args.prior_configs[i]
        configs_to_models[args.prior_configs[i]] = model_idx
        cfg = MsBayesConfig(args.prior_configs[i])
        assert cfg.npairs > 0
        if not num_taxon_pairs:
            num_taxon_pairs = cfg.npairs
        else:
            if num_taxon_pairs != cfg.npairs:
                raise ValueError('prior configs have different numbers of '
                        'taxon pairs')
    info.write('\t[[prior_configs]]\n')
    for model_idx, cfg in models_to_configs.iteritems():
        info.write('\t\t{0} = {1}\n'.format(model_idx, cfg))

    for config in args.observed_configs:
        cfg = MsBayesConfig(config)
        assert cfg.npairs > 0
        if not num_taxon_pairs:
            num_taxon_pairs = cfg.npairs
        else:
            if num_taxon_pairs != cfg.npairs:
                raise ValueError('observed config {0} has {1} taxon pairs, '
                        'whereas the prior configs have {2} pairs'.format(
                                config, cfg.npairs, num_taxon_pairs))

    ##########################################################################
    ## begin analysis --- get observed summary stats

    set_memory_trace() # start logging memory profile
    start_time = datetime.datetime.now()

    obs_temp_dir = base_temp_dir
    if args.staging_dir:
        obs_temp_dir = args.staging_dir
    observed_temp_fs = TempFileSystem(parent = obs_temp_dir,
            prefix = 'observed-temps-')

    if args.reps < 1:
        _LOG.info('Calculating summary statistics from sequence data...')
        obs_workers = []
        for i, cfg in enumerate(args.observed_configs):
            ss_worker = ObsSumStatsWorker(
                    temp_fs = observed_temp_fs,
                    config_path = cfg,
                    output_path = observed_paths[i],
                    schema = 'abctoolbox',
                    stat_patterns = stat_patterns)
            obs_workers.append(ss_worker)

        obs_workers = Manager.run_workers(
            workers = obs_workers,
            num_processors = args.np)

    else:
        _LOG.info('Simulating summary statistics from observed configs...')
        num_observed_workers = min([args.reps, args.np])
        if args.reps <= args.np:
            observed_batch_size = 1
            remainder = 0
        else:
            observed_batch_size, remainder = long_division(args.reps, args.np)
        msbayes_workers = []
        for idx, cfg in enumerate(args.observed_configs):
            observed_model_idx = configs_to_models.get(cfg,
                    None)
            schema = 'abctoolbox'
            for i in range(num_observed_workers):
                worker = MsBayesWorker(
                        temp_fs = observed_temp_fs,
                        sample_size = observed_batch_size,
                        config_path = cfg,
                        model_index = observed_model_idx,
                        report_parameters = True,
                        schema = schema,
                        include_header = True,
                        stat_patterns = stat_patterns,
                        write_stats_file = True,
                        staging_dir = None,
                        tag = idx)
                msbayes_workers.append(worker)
            if remainder > 0:
                worker = MsBayesWorker(
                        temp_fs = observed_temp_fs,
                        sample_size = remainder,
                        config_path = cfg,
                        model_index = observed_model_idx,
                        report_parameters = True,
                        schema = schema,
                        include_header = True,
                        stat_patterns = stat_patterns,
                        write_stats_file = True,
                        staging_dir = None,
                        tag = idx)
                msbayes_workers.append(worker)

        # run parallel msbayes processes
        msbayes_workers = Manager.run_workers(
            workers = msbayes_workers,
            num_processors = args.np)

        workers = dict(zip(range(len(args.observed_configs)),
                [[] for i in range(len(args.observed_configs))]))
        for w in msbayes_workers:
            workers[w.tag].append(w)

        # merge simulated observed data into one file
        for i in range(len(args.observed_configs)):
            merge_prior_files([w.prior_path for w in workers[i]],
                    observed_paths[i])
            lc = line_count(observed_paths[i], ignore_headers=True)
            if lc != args.reps:
                raise Exception('The number of observed simulations ({0}) '
                        'generated for observed config {1!r} and output to '
                        'file {2!r} does not match the number of reps '
                        '({3})'.format(lc, args.observed_configs[i],
                            observed_paths[i], args.reps))
    if not args.keep_temps:
        _LOG.debug('purging observed temps...')
        observed_temp_fs.purge()

    ##########################################################################
    ## Begin ABC analyses

    abc_team = ABCTeam(
            temp_fs = temp_fs,
            observed_stats_files = observed_paths,
            num_taxon_pairs = num_taxon_pairs,
            config_paths = args.prior_configs,
            previous_prior_dir = previous_prior_dir,
            num_prior_samples = args.num_prior_samples,
            num_processors = args.np,
            num_standardizing_samples = args.num_standardizing_samples,
            num_posterior_samples = args.num_posterior_samples,
            num_posterior_density_quantiles = args.num_posterior_quantiles,
            batch_size = args.prior_batch_size,
            output_dir = base_dir,
            output_prefix = args.output_prefix,
            prior_temp_dir = args.staging_dir,
            rng = GLOBAL_RNG,
            report_parameters = True,
            stat_patterns = stat_patterns,
            abctoolbox_bandwidth = args.bandwidth,
            omega_threshold = 0.01,
            compress = args.compress,
            reporting_frequency = args.reporting_frequency,
            keep_temps = args.keep_temps,
            global_estimate_only = False,
            global_estimate = not args.no_global_estimate,
            generate_prior_samples_only = args.generate_samples_only)
    abc_team.run()

    stop_time = datetime.datetime.now()
    _LOG.info('Done!')
    info.write('\t[[run_stats]]\n', _LOG.info)
    info.write('\t\tstart_time = {0}\n'.format(str(start_time)), _LOG.info)
    info.write('\t\tstop_time = {0}\n'.format(str(stop_time)), _LOG.info)
    info.write('\t\ttotal_duration = {0}\n'.format(str(stop_time - start_time)),
            _LOG.info)

    if not args.keep_temps:
        _LOG.debug('purging temps...')
        temp_fs.purge()

if __name__ == '__main__':
    main_cli()

