from __future__ import annotations

import torch

from isaaclab.envs import ManagerBasedRLEnv

from .mdp.rewards import accumulate_v23_raw_metrics, reset_v23_raw_metric_extras


class SpotMicroManagerBasedRLEnv(ManagerBasedRLEnv):
    def __init__(self, cfg, render_mode=None, **kwargs):
        super().__init__(cfg, render_mode=render_mode, **kwargs)
        # V66: Phase randomization (대각 편향 방지)
        from .spot_micro_rl_env_cfg import TRAIN_VERSION
        if TRAIN_VERSION.startswith("V66"):
            self._v66_phase_random_enabled = True

    def step(self, action: torch.Tensor):
        action = action.to(self.device)
        warmup_steps = int(getattr(self.cfg, "action_warmup_steps", 0))
        if warmup_steps > 0:
            warmup_mask = (self.episode_length_buf < warmup_steps).unsqueeze(1)
            if torch.any(warmup_mask):
                action = torch.where(warmup_mask, torch.zeros_like(action), action)

        self.action_manager.process_action(action)
        if warmup_steps > 0 and hasattr(self, "_action_ramp_joint_pos0"):
            ramp_mask = self.episode_length_buf < warmup_steps
            if torch.any(ramp_mask):
                joint_term = self.action_manager.get_term("joint_pos")
                target = joint_term.processed_actions
                alpha = (self.episode_length_buf.float() / float(warmup_steps)).unsqueeze(1)
                alpha = torch.clamp(alpha, 0.0, 1.0)
                start = self._action_ramp_joint_pos0
                ramped = start + alpha * (target - start)
                joint_term._processed_actions = torch.where(ramp_mask.unsqueeze(1), ramped, target)

        self.recorder_manager.record_pre_step()
        is_rendering = self.sim.has_gui() or self.sim.has_rtx_sensors()

        for _ in range(self.cfg.decimation):
            self._sim_step_counter += 1
            self.action_manager.apply_action()
            self.scene.write_data_to_sim()
            self.sim.step(render=False)
            self.recorder_manager.record_post_physics_decimation_step()
            if self._sim_step_counter % self.cfg.sim.render_interval == 0 and is_rendering:
                self.sim.render()
            self.scene.update(dt=self.physics_dt)

        self.episode_length_buf += 1
        self.common_step_counter += 1
        self.reset_buf = self.termination_manager.compute()
        self.reset_terminated = self.termination_manager.terminated
        self.reset_time_outs = self.termination_manager.time_outs
        self.reward_buf = self.reward_manager.compute(dt=self.step_dt)
        accumulate_v23_raw_metrics(self)

        if len(self.recorder_manager.active_terms) > 0:
            self.obs_buf = self.observation_manager.compute()
            self.recorder_manager.record_post_step()

        reset_env_ids = self.reset_buf.nonzero(as_tuple=False).squeeze(-1)
        if len(reset_env_ids) > 0:
            self.recorder_manager.record_pre_reset(reset_env_ids)
            self._reset_idx(reset_env_ids)

            if self.sim.has_rtx_sensors() and self.cfg.num_rerenders_on_reset > 0:
                for _ in range(self.cfg.num_rerenders_on_reset):
                    self.sim.render()

            self.recorder_manager.record_post_reset(reset_env_ids)

        # V58.B4 3-Phase curriculum: command 범위를 iteration에 따라 자동 변경
        self._b4_phase_update()
        self.command_manager.compute(dt=self.step_dt)
        if "interval" in self.event_manager.available_modes:
            self.event_manager.apply(mode="interval", dt=self.step_dt)
        self.obs_buf = self.observation_manager.compute(update_history=True)

        return self.obs_buf, self.reward_buf, self.reset_terminated, self.reset_time_outs, self.extras

    def _reset_idx(self, env_ids):
        raw_metric_extras = reset_v23_raw_metric_extras(self, env_ids)
        super()._reset_idx(env_ids)
        warmup_steps = int(getattr(self.cfg, "action_warmup_steps", 0))
        if warmup_steps > 0 and "joint_pos" in self.action_manager.active_terms:
            joint_term = self.action_manager.get_term("joint_pos")
            if not hasattr(self, "_action_ramp_joint_pos0"):
                self._action_ramp_joint_pos0 = torch.zeros(
                    self.num_envs, joint_term.action_dim, device=self.device, dtype=self.scene["robot"].data.joint_pos.dtype
                )
            self._action_ramp_joint_pos0[env_ids] = self.scene["robot"].data.joint_pos[env_ids][:, joint_term._joint_ids]
        if raw_metric_extras:
            self.extras.setdefault("log", {}).update(raw_metric_extras)

    def _b4_phase_update(self):
        """V58.B4 3-Phase auto curriculum."""
        phase2 = getattr(self.cfg, "_b4_phase2_iter", 0)
        phase3 = getattr(self.cfg, "_b4_phase3_iter", 0)
        if phase2 == 0 and phase3 == 0:
            return  # not B4

        # iteration 추정: common_step_counter / (max_episode_length)
        max_ep = int(self.max_episode_length) if hasattr(self, 'max_episode_length') and self.max_episode_length > 0 else 1000
        iteration = self.common_step_counter // max_ep

        cmd_term = self.command_manager._terms.get("base_velocity", None)
        if cmd_term is None:
            return

        if iteration < phase2:
            new_standing = 1.0
            new_vel_x = (0.0, 0.0)
            new_ang_z = (0.0, 0.0)
        elif iteration < phase3:
            new_standing = 0.5
            new_vel_x = (0.0, 0.2)
            new_ang_z = (-0.1, 0.1)
        else:
            new_standing = 0.2
            new_vel_x = (0.0, 0.4)
            new_ang_z = (-0.2, 0.2)

        cmd_term.cfg.rel_standing_envs = new_standing
        cmd_term.cfg.ranges.lin_vel_x = new_vel_x
        cmd_term.cfg.ranges.ang_vel_z = new_ang_z
