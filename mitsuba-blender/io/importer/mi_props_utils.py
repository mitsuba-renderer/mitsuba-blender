
def named_references_with_class(mi_context, mi_props, cls):
    result = []
    for _, ref_id in mi_props.references():
        props = mi_context.mi_scene_props.get_with_id_and_class(ref_id, cls)
        if props is not None:
            result.append(props)
    return result
