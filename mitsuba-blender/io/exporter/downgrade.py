from os import path as osp
import re
import xml.etree.ElementTree as ET

# from ipdb import set_trace

def convert(fname, mode="v1"):
  from inflection import camelize, underscore
  dname = osp.dirname(fname)
  base = osp.basename(fname)
  # check ext
  base, ext = osp.splitext(base)
  
  if ext != ".xml":
    print(f"Wrong file format {ext}")
    return False
  # check version if already in correct format than do nothing
  tree = ET.parse(fname)
  root = tree.getroot()
  version = root.attrib["version"]
  MAJOR_VER = int(version[0])

  if mode == "v1":
    if MAJOR_VER < 2:
      print(f"Already in correct version {version}")
      return True
    else:
      root.attrib["version"] = "0.6.0"
  elif mode == "v2":
    if MAJOR_VER > 0:
      print(f"Already in correct version {version}")
      return True
    else:
      root.attrib["version"] = "2.1.0"

  # TODO : don't change filenames

  f_str = ET.tostring(root).decode('utf-8')
  if mode == "v1":
    # converting to 0.6.0 version
    # snake_case to camelCase 
    modified_str = camelize(f_str)
    root_n = ET.fromstring(modified_str)

    # ior
    for i, ele_n in enumerate(root_n.findall(".//*[@name='intIor']")):
      # print("Copying back %s"%ele_n)
      ele_n.attrib["name"] = "intIOR"

    for i, ele_n in enumerate(root_n.findall(".//*[@name='extIor']")):
      # print("Copying back %s"%ele_n)
      ele_n.attrib["name"] = "extIOR"

    # copy back the filename
    ele_iter = root.findall(".//*[@filename]")
    for i, ele_n in enumerate(root_n.findall(".//*[@filename]")):
      # print("Copying back %s"%ele_n)
      ele = ele_iter[i]
      ele_n.attrib["filename"] = ele.attrib["filename"]

    ele_iter = root.findall(".//*[@name='filename']")
    for i, ele_n in enumerate(root_n.findall(".//*[@name='filename']")):
      # print("Copying back %s"%ele_n)
      ele = ele_iter[i]
      ele_n.attrib["value"] = ele.attrib["value"]
    
    # translation
    for ele in root_n.findall(".//translate"):
      val = ele.attrib.pop("value")
      x, y, z = val.split(" ")
      ele.attrib["x"] = x
      ele.attrib["y"] = y
      ele.attrib["z"] = z

    # include filename
    for ele in root_n.findall(".//include"):
      val = ele.attrib["filename"]
      core, ext = osp.splitext(val)
      ele.attrib["filename"] = f"{core}_v1{ext}"

    # lookat -> lookAt
    # for ele in root.findall(".//transform"):
    #   ele

    # write the file
    modified_str = ET.tostring(root_n).decode('utf-8')
    with open(osp.join(dname, f"{base}_v1.xml"), "w") as f:
      f.write(modified_str)
    # ET.write(osp.join(dname, f"{base}_v1.xml"))
    
  elif mode == "v2":
    modified_str = underscore(f_str)
    with open(osp.join(dname, f"{base}_v2.xml"), "w") as f:
      f.write(modified_str)