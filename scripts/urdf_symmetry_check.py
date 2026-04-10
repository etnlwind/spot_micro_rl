"""URDF 좌우 대칭 검증 스크립트 (V63.I.1 비대칭 디버그).

SpotMicro URDF의 link mass, inertia, joint origin/axis 를 L/R 으로 비교해
좌우 비대칭 요소를 찾는다.
"""
import re
from pathlib import Path
from xml.etree import ElementTree as ET

URDF = Path("/mnt/d/project/spot_micro_rl/assets/robots/spot_micro/spotmicroai_realistic_inertia.urdf")


def parse_float_list(s):
    return [float(x) for x in s.strip().split()]


def link_info(link):
    """Extract mass, inertia, inertial origin from link element."""
    inertial = link.find("inertial")
    if inertial is None:
        return None
    mass_el = inertial.find("mass")
    mass = float(mass_el.get("value")) if mass_el is not None else None
    inertia_el = inertial.find("inertia")
    inertia = None
    if inertia_el is not None:
        inertia = {k: float(inertia_el.get(k)) for k in
                   ("ixx", "ixy", "ixz", "iyy", "iyz", "izz")}
    origin_el = inertial.find("origin")
    origin = None
    if origin_el is not None:
        xyz = parse_float_list(origin_el.get("xyz", "0 0 0"))
        rpy = parse_float_list(origin_el.get("rpy", "0 0 0"))
        origin = {"xyz": xyz, "rpy": rpy}
    return {"mass": mass, "inertia": inertia, "origin": origin}


def joint_info(joint):
    origin_el = joint.find("origin")
    xyz = parse_float_list(origin_el.get("xyz", "0 0 0")) if origin_el is not None else [0, 0, 0]
    rpy = parse_float_list(origin_el.get("rpy", "0 0 0")) if origin_el is not None else [0, 0, 0]
    axis_el = joint.find("axis")
    axis = parse_float_list(axis_el.get("xyz", "0 0 0")) if axis_el is not None else [0, 0, 0]
    limit_el = joint.find("limit")
    limit = None
    if limit_el is not None:
        limit = {
            "lower": float(limit_el.get("lower", "0")),
            "upper": float(limit_el.get("upper", "0")),
            "effort": float(limit_el.get("effort", "0")),
            "velocity": float(limit_el.get("velocity", "0")),
        }
    return {"xyz": xyz, "rpy": rpy, "axis": axis, "limit": limit, "type": joint.get("type")}


def pair_key(name):
    """Return (pair_id, side) where side in {'left','right','neutral'}."""
    if "front_left" in name:
        return (name.replace("front_left", "front_X"), "left")
    if "front_right" in name:
        return (name.replace("front_right", "front_X"), "right")
    if "rear_left" in name:
        return (name.replace("rear_left", "rear_X"), "left")
    if "rear_right" in name:
        return (name.replace("rear_right", "rear_X"), "right")
    return (name, "neutral")


def main():
    tree = ET.parse(URDF)
    root = tree.getroot()

    # Collect link info
    links = {}
    for link in root.findall("link"):
        name = link.get("name")
        info = link_info(link)
        if info is not None:
            links[name] = info

    # Collect joint info
    joints = {}
    for joint in root.findall("joint"):
        name = joint.get("name")
        joints[name] = joint_info(joint)

    # Group links by pair
    link_pairs = {}
    for name, info in links.items():
        key, side = pair_key(name)
        if side == "neutral":
            continue
        link_pairs.setdefault(key, {})[side] = (name, info)

    joint_pairs = {}
    for name, info in joints.items():
        key, side = pair_key(name)
        if side == "neutral":
            continue
        joint_pairs.setdefault(key, {})[side] = (name, info)

    # Compare links
    print("=" * 70)
    print("LINK L/R COMPARISON (mass, inertia, inertial origin)")
    print("=" * 70)
    mismatch_count = 0
    for key in sorted(link_pairs.keys()):
        sides = link_pairs[key]
        if "left" not in sides or "right" not in sides:
            continue
        L_name, L = sides["left"]
        R_name, R = sides["right"]

        issues = []
        # Mass
        if L["mass"] is not None and R["mass"] is not None:
            if abs(L["mass"] - R["mass"]) > 1e-9:
                issues.append(f"mass L={L['mass']} R={R['mass']}")

        # Inertia — all components should be SAME, except ixy/iyz/ixz may flip sign for mirrored
        if L["inertia"] is not None and R["inertia"] is not None:
            for k in ("ixx", "iyy", "izz"):
                if abs(L["inertia"][k] - R["inertia"][k]) > 1e-9:
                    issues.append(f"{k} L={L['inertia'][k]:.3e} R={R['inertia'][k]:.3e}")
            # off-diagonal: mirror should flip sign on ixy and iyz (reflecting across xz plane)
            for k in ("ixy", "iyz"):
                if abs(L["inertia"][k] + R["inertia"][k]) > 1e-9:
                    issues.append(f"{k} L={L['inertia'][k]:.3e} R={R['inertia'][k]:.3e} (expected opposite)")
            # ixz should be same (both sides have same fore-aft)
            if abs(L["inertia"]["ixz"] - R["inertia"]["ixz"]) > 1e-9:
                issues.append(f"ixz L={L['inertia']['ixz']:.3e} R={R['inertia']['ixz']:.3e}")

        # Origin — y should be opposite sign
        if L["origin"] is not None and R["origin"] is not None:
            Lx, Ly, Lz = L["origin"]["xyz"]
            Rx, Ry, Rz = R["origin"]["xyz"]
            if abs(Lx - Rx) > 1e-9:
                issues.append(f"origin.x L={Lx} R={Rx}")
            if abs(Ly + Ry) > 1e-9:
                issues.append(f"origin.y L={Ly} R={Ry} (expected opposite)")
            if abs(Lz - Rz) > 1e-9:
                issues.append(f"origin.z L={Lz} R={Rz}")

        if issues:
            mismatch_count += 1
            print(f"\n❌ {key}")
            print(f"   L: {L_name}")
            print(f"   R: {R_name}")
            for iss in issues:
                print(f"   - {iss}")
    if mismatch_count == 0:
        print("\n✅ All link pairs mirror-symmetric")

    print()
    print("=" * 70)
    print("JOINT L/R COMPARISON (origin, axis, limit)")
    print("=" * 70)
    joint_mismatch = 0
    for key in sorted(joint_pairs.keys()):
        sides = joint_pairs[key]
        if "left" not in sides or "right" not in sides:
            continue
        L_name, L = sides["left"]
        R_name, R = sides["right"]

        issues = []
        # Origin.xyz — y should be opposite
        Lx, Ly, Lz = L["xyz"]
        Rx, Ry, Rz = R["xyz"]
        if abs(Lx - Rx) > 1e-9:
            issues.append(f"origin.x L={Lx} R={Rx}")
        if abs(Ly + Ry) > 1e-9:
            issues.append(f"origin.y L={Ly} R={Ry} (expected opposite)")
        if abs(Lz - Rz) > 1e-9:
            issues.append(f"origin.z L={Lz} R={Rz}")

        # Origin.rpy — roll should be opposite, pitch/yaw same
        Lr, Lp, Lyw = L["rpy"]
        Rr, Rp, Ryw = R["rpy"]
        if abs(Lr + Rr) > 1e-9 and abs(Lr - Rr) > 1e-9:
            issues.append(f"rpy.roll L={Lr} R={Rr}")
        if abs(Lp - Rp) > 1e-9:
            issues.append(f"rpy.pitch L={Lp} R={Rp}")
        if abs(Lyw - Ryw) > 1e-9:
            issues.append(f"rpy.yaw L={Lyw} R={Ryw}")

        # Axis — must be identical (L/R same joint axis convention)
        if L["axis"] != R["axis"]:
            issues.append(f"axis L={L['axis']} R={R['axis']}")

        # Limit
        if L["limit"] and R["limit"]:
            for k in ("lower", "upper", "effort", "velocity"):
                if abs(L["limit"][k] - R["limit"][k]) > 1e-9:
                    issues.append(f"limit.{k} L={L['limit'][k]} R={R['limit'][k]}")

        if issues:
            joint_mismatch += 1
            print(f"\n❌ {key}")
            print(f"   L: {L_name}")
            print(f"   R: {R_name}")
            for iss in issues:
                print(f"   - {iss}")

    if joint_mismatch == 0:
        print("\n✅ All joint pairs mirror-symmetric")

    print()
    print("=" * 70)
    print(f"SUMMARY: {mismatch_count} link pairs, {joint_mismatch} joint pairs with issues")
    print("=" * 70)


if __name__ == "__main__":
    main()
