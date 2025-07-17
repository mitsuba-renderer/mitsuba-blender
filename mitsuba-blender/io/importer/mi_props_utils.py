def get_references_by_type(mi_context, mi_props, target_types):
    '''
    Return a list of references in `mi_props` that are one of the specified `target_types`.
    '''
    from mitsuba import Properties
    references = []
    for _, val in mi_props.items():
        if isinstance(val, Properties.ResolvedReference):
            mi_node = mi_context.mi_state.nodes[val.index()]
            if mi_node.type in target_types:
                references.append(val.index())
    return references

