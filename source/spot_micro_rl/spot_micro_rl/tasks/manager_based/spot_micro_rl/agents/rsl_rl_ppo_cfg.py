# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from isaaclab.utils import configclass

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg


@configclass
class PPORunnerCfg(RslRlOnPolicyRunnerCfg):
    """V17: Flat terrain PPO 학습 설정.
    
    V17: Boston Dynamics Spot 같은 느리고 큰 보폭의 걸음걸이를 위해
    rollout 길이를 48 스텝(1.92초)으로 확장. 걸음걸이 주기(0.3~0.5s)를
    여러 사이클 포함하여 학습 안정성 향상.
    """
    num_steps_per_env = 48  # V17: 24→48 (1.92s, 걸음걸이 3~6 사이클 포함)
    max_iterations = 15000
    save_interval = 200
    experiment_name = "spot_micro_flat"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_obs_normalization=False,
        critic_obs_normalization=False,
        actor_hidden_dims=[512, 256, 128],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=0.5,
        use_clipped_value_loss=True,
        clip_param=0.1,  # V15d: 0.2→0.1 (보수적 업데이트)
        entropy_coef=0.01,
        num_learning_epochs=3,  # V15d: 5→3 (배치당 과적합 방지)
        num_mini_batches=4,
        learning_rate=1.0e-4,  # V15d: 3e-4→1e-4 (안정성 극대화)
        schedule="fixed",
        gamma=0.97,  # V15d: 0.99→0.97 (return 크기 3x 축소)
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


@configclass
class PPORoughRunnerCfg(RslRlOnPolicyRunnerCfg):
    """SpotMicro 러프 지형 PPO 학습 설정.
    
    높이 스캔 관측이 추가되어 관측 차원이 커지므로
    네트워크 크기를 유지하되 iterations를 늘림.
    """
    num_steps_per_env = 24
    max_iterations = 10000
    save_interval = 100
    experiment_name = "spot_micro_rough"
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_obs_normalization=False,
        critic_obs_normalization=False,
        actor_hidden_dims=[512, 256, 128],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,  # 러프 지형에서 탐색 줄임 (안정성 우선)
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-4,  # V14b: 5e-4→1e-4 (크리틱 발산 방지)
        schedule="fixed",  # V14: adaptive→fixed (noise std 폭발 방지)
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )
