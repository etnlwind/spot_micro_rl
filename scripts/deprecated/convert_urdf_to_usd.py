#!/usr/bin/env python3
"""Convert SpotMicro URDF to USD format."""

import argparse
import os
from pathlib import Path

import isaaclab.sim as sim_utils
from omni.isaac.lab.sim.converters import UrdfConverter, UrdfConverterCfg


def main():
    """Convert URDF to USD."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Convert SpotMicro URDF to USD")
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="Output directory for USD file. Defaults to same directory as URDF."
    )
    args = parser.parse_args()

    # Get paths
    script_dir = Path(__file__).resolve().parent.parent
    urdf_path = script_dir / "assets" / "robots" / "spot_micro" / "spotmicroai_realistic_inertia.urdf"
    
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = urdf_path.parent
    
    output_dir.mkdir(parents=True, exist_ok=True)
    usd_path = output_dir / "spotmicroai_realistic_inertia.usd"
    
    print(f"Converting URDF to USD...")
    print(f"  Input:  {urdf_path}")
    print(f"  Output: {usd_path}")
    
    # Configure URDF converter
    converter_cfg = UrdfConverterCfg(
        asset_path=str(urdf_path),
        usd_dir=str(output_dir),
        usd_file_name="spotmicroai_realistic_inertia.usd",
        fix_base=False,
        merge_fixed_joints=True,
        force_usd_conversion=True,
        make_instanceable=False,
        joint_drive=UrdfConverterCfg.JointDriveCfg(
            gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                stiffness=0.0,
                damping=0.0,
            ),
            target_type="position",
        ),
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            disable_gravity=False,
            max_depenetration_velocity=1.0,
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=4,
            solver_velocity_iteration_count=0,
        ),
    )
    
    # Convert
    converter = UrdfConverter(converter_cfg)
    print(f"\n✓ Conversion complete!")
    print(f"  USD file saved to: {usd_path}")


if __name__ == "__main__":
    main()
