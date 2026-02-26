# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

from isaaclab.utils import configclass

from isaaclab_rl.rsl_rl import RslRlOnPolicyRunnerCfg, RslRlPpoActorCriticCfg, RslRlPpoAlgorithmCfg


@configclass
class PPORunnerCfg(RslRlOnPolicyRunnerCfg):
    """V15: Flat terrain PPO 학습 설정.
    
    V14b까지 critic reset + fine-tune 전략이 3연속 발산.
    V15는 처음부터 뒷다리 보상을 포함해서 from-scratch 학습.
    Fixed schedule로 noise std 폭발 방지.
    """
    num_steps_per_env = 24
    max_iterations = 15000  # V15: from-scratch는 더 오래 학습
    save_interval = 200  # V15: 세밀한 체크포인트
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
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.01,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=5.0e-4,  # V15: 1e-3→5e-4 (안정적 학습)
        schedule="fixed",  # V15: adaptive→fixed (noise std 폭발 방지)
        gamma=0.99,
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
