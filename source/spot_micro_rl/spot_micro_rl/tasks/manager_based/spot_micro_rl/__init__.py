# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

import gymnasium as gym

from . import agents

##
# Register Gym environments.
##


gym.register(
    id="Isaac-Velocity-Flat-SpotMicro-v0",
    entry_point=f"{__name__}.spot_micro_rl_env:SpotMicroManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.spot_micro_rl_env_cfg:SpotMicroFlatEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:PPORunnerCfg",
    },
)

gym.register(
    id="Isaac-Velocity-Rough-SpotMicro-v0",
    entry_point=f"{__name__}.spot_micro_rl_env:SpotMicroManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.spot_micro_rl_env_cfg:SpotMicroRoughEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:PPORoughRunnerCfg",
    },
)

gym.register(
    id="Isaac-Velocity-Rough-SpotMicro-Play-v0",
    entry_point=f"{__name__}.spot_micro_rl_env:SpotMicroManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.spot_micro_rl_env_cfg:SpotMicroRoughEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:PPORoughRunnerCfg",
    },
)

gym.register(
    id="Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0",
    entry_point=f"{__name__}.spot_micro_rl_env:SpotMicroManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.spot_micro_rl_env_cfg:SpotMicroFlatOnSteepSlopePlayCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:PPORunnerCfg",
    },
)