# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/200_optuna.ipynb (unless otherwise specified).

__all__ = ['optuna_study']

# Cell
from pathlib import Path
from fastcore.script import *
import joblib
from .imports import *
from importlib import import_module
import warnings
warnings.filterwarnings("ignore")


@call_parse
def optuna_study(
    config:             Param('Path to the study config file', str),
    study_type:         Param('Type of study', str)=None,
    multivariate:       Param('Flag to show progress bars or not.', store_false)=True,
    study_name:         Param("Study's name. If this argument is set to None, a unique name is generated automatically.", str)=None,
    seed:               Param('Seed for random number generator.', int)=None,
    search_space:       Param('Path to dictionary whose keys and values are a parameter name and the corresponding candidates of values', str)=None,
    direction:          Param('Direction of optimization.', str)='maximize',
    n_trials:           Param('The number of trials.', int)=None,
    timeout:            Param('Stop study after the given number of second(s).', int)=None,
    gc_after_trial:     Param('Flag to determine whether to automatically run garbage collection after each trial.', store_true)=False,
    show_progress_bar:  Param('Flag to show progress bars or not.', store_false)=True,
    show_plots:         Param('Flag to show plots or not.', store_false)=True,
    save:               Param('Flag to save study to disk or not.', store_false)=True,
    path:               Param('Path where the study will be saved', str)='optuna',
    verbose:            Param('Verbose.', store_true)=False,
    ):

    try: import optuna
    except ImportError: raise ImportError('You need to install optuna!')

    while True:
        if config[0] in "/ .": config = config.split(config[0], 1)[1]
        else: break
    if '/' in config and config.rsplit('/', 1)[0] not in sys.path: sys.path.append(config.rsplit('/', 1)[0])
    if sys.path[0] != './': sys.path = ['./'] + sys.path
    m = import_file_as_module(config)
    assert hasattr(m, 'objective'), f"there's no objective function in {config}"
    objective = getattr(m, "objective")

    if study_type is None or study_type.lower() == "bayesian": sampler = optuna.samplers.TPESampler(seed=seed, multivariate=multivariate)
    elif study_type.lower() in ["gridsearch", "gridsampler"]:
        assert hasattr(m, 'search_space'), f"there's no search_space function in {search_space}"
        search_space = getattr(m, 'search_space')
        sampler = optuna.samplers.GridSampler(search_space=search_space)
    elif study_type.lower() in ["randomsearch", "randomsampler"]: sampler = optuna.samplers.RandomSampler(seed=seed)

    try:
        study = optuna.create_study(sampler=sampler, study_name=study_name, direction=direction)
        study.optimize(objective, n_trials=n_trials, timeout=timeout, gc_after_trial=gc_after_trial, show_progress_bar=show_progress_bar)

    except KeyboardInterrupt:
        pass

    if save:
        full_path = Path(path)/f'{study.study_name}.pkl'
        full_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(study, full_path)
        print(f'\nOptuna study saved to {full_path}')
        print(f"To reload the study run: study = joblib.load('{full_path}')")

    if show_plots and len(study.trials) > 1:
        try: display(optuna.visualization.plot_optimization_history(study))
        except: pass
        try: display(optuna.visualization.plot_param_importances(study))
        except: pass
        try: display(optuna.visualization.plot_slice(study))
        except: pass
        try: display(optuna.visualization.plot_parallel_coordinate(study))
        except: pass

    try:
        print(f"\nStudy stats   : ")
        print(f"===============")
        print(f"Study name    : {study.study_name}")
        print(f"  n_trials    : {len(study.trials)}")
        print(f"Best trial    :")
        trial = study.best_trial
        print(f"  value       : {trial.value}")
        print(f"  best_params = {trial.params}\n")
    except:
        print('No trials are completed yet.')
    return study