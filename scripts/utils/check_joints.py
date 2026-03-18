import xml.etree.ElementTree as ET
tree = ET.parse(r'D:\project\spot_micro_rl\assets\robots\spot_micro\spotmicroai_realistic_inertia.urdf')
root = tree.getroot()
for j in root.findall('.//joint'):
    jtype = j.get('type')
    if jtype in ('revolute', 'continuous'):
        limit = j.find('limit')
        if limit is not None:
            name = j.get('name')
            lo = limit.get('lower')
            hi = limit.get('upper')
            print(f"{name:30s} lower={lo:>8s} upper={hi:>8s}")
