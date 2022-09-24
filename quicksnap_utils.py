﻿import bpy, mathutils, logging
from mathutils import Vector
from enum import Enum

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = 1
    SOURCE_PICKED = 2
    DESTINATION_PICKED = 3


def transform_worldspace_viewspace(world_space_coord, perspective_matrix):
    return perspective_matrix @ Vector((world_space_coord[0], world_space_coord[1], world_space_coord[2], 1.0))


def transform_viewspace_coord2d(view_space_coord, width_half, height_half):
    return Vector((width_half + width_half * (view_space_coord.x / view_space_coord.w),
                   height_half + height_half * (view_space_coord.y / view_space_coord.w),
                   ))


def transform_worldspace_coord2d(world_space_coord, region, region3d):
    return transform_viewspace_coord2d(transform_worldspace_viewspace(world_space_coord, region3d.perspective_matrix),
                                       region.width / 2.0, region.height / 2.0)


def get_selection_meshes():
    return [obj for obj in bpy.context.selected_objects if
            obj.visible_get() and (obj.type == 'MESH' or obj.type == 'CURVE')]


def get_scene_meshes(exclude_selection=False):
    if exclude_selection:
        objects = [obj.name for obj in bpy.data.objects if
                   obj not in bpy.context.selected_objects and obj.visible_get() and (
                               obj.type == 'MESH' or obj.type == 'CURVE')]
    else:
        objects = [obj.name for obj in bpy.data.objects if
                   obj.visible_get() and (obj.type == 'MESH' or obj.type == 'CURVE')]
    return objects


def include_children(objects, recursive_call=False):
    """
    Inputs a list of objects, outputs that list + children objects
    """

    result = []
    if type(objects) is list or type(objects) is set:
        if not recursive_call:
            objects = keep_only_parents(objects)
        for obj in objects:
            result.extend(include_children(obj, recursive_call=True))
    else:
        obj = objects
        result.append(obj)
        for child in obj.children:
            result.extend(include_children(child, recursive_call=True))
    return result


def keep_only_parents(objects):
    """
    Inputs a list of objects, outputs that list minus all children of objects in that list
    """
    objects = set(objects)
    return set([obj for obj in objects if not has_parent(obj, objects)])


def has_parent(obj, parent_list):
    """
    Returns True of the object has a parent among a list of objects
    """
    parent = obj.parent
    if parent == None:
        return False
    if parent in parent_list:
        return True
    return has_parent(parent, parent_list)


def set_object_mode_if_needed():
    """
    Set context to object mode, returns the previous mode.
    """
    # logger.info("entering object mode if needed")
    mode = f'{bpy.context.active_object.mode}'
    if mode == 'EDIT':
        # logger.info('Going to Object Mode')
        bpy.ops.object.mode_set(mode='OBJECT')
    return mode


def revert_mode(previous_mode):
    if bpy.context.active_object.mode != previous_mode:
        bpy.ops.object.mode_set(mode=previous_mode)


def translate_object_worldspace(obj, translation):
    obj.matrix_world = translation @ obj.matrix_world


def translate_vertices_worldspace(obj, bmesh, backup_vertices, translation):
    if hasattr(bmesh.verts, "ensure_lookup_table"):
        bmesh.verts.ensure_lookup_table()
    world_matrix = obj.matrix_world
    world_matrix_inverted = world_matrix.copy().inverted()
    for (index, co, _, _, _, _) in backup_vertices:
        bmesh.verts[index].co = world_matrix_inverted @ translation @ world_matrix @ co
    bmesh.to_mesh(obj.data)


def dump(obj):
    print(f"\n\n=============== Dump({obj}) ===============")
    for attr in dir(obj):
        if hasattr(obj, attr):
            print(f'{attr} : {getattr(obj, attr)}')
    print(f"=============== END Dump({obj}) ===============\n\n")


def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None


def get_axis_target(origin, target, axis_constraint, obj=None):
    """
    Returns the snapping target taking into account constrain options
    if obj is not None the constraint will be calculated in object space.
    """
    if len(axis_constraint) == 0:
        return target
    if obj is None:
        world_matrix = mathutils.Matrix.Identity(4)
    else:
        world_matrix = obj.matrix_world.to_quaternion()

    # Axis constraint
    if len(axis_constraint) == 1:
        if axis_constraint == 'X':
            point2 = origin + world_matrix @ Vector((1, 0, 0))
        elif axis_constraint == 'Y':
            point2 = origin + world_matrix @ Vector((0, 1, 0))
        else:
            point2 = origin + world_matrix @ Vector((0, 0, 1))
        return mathutils.geometry.intersect_point_line(target, origin, point2)[0]

    # Planar constraint
    if len(axis_constraint) == 2:
        if axis_constraint == 'XY':
            point2 = origin + world_matrix @ Vector((1, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 1, 0))
        elif axis_constraint == 'YZ':
            point2 = origin + world_matrix @ Vector((0, 1, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1))
        else:
            point2 = origin + world_matrix @ Vector((1, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1))

        normal = mathutils.geometry.normal(origin, point2, point3)
        if not normal.dot(origin - target) > 0:  # flip normal if it is pointing the wrong direction
            normal = -1 * normal
        new_target = mathutils.geometry.intersect_ray_tri(origin, point2, point3, normal, target, False)
        return new_target


def get_target_free(origin, camera_position, camera_vector, snapping, obj=None):
    """
    Get the target position if there is no target point, taking constraint into consideration.
    If obj is not None the constraint will be calculated in object space.
    """
    camera_point_b = camera_position + camera_vector

    # If no constraint target will be the intersection between the mouse ray and the plane perpendicular to camera
    # at origin position
    if len(snapping) == 0:
        return mathutils.geometry.intersect_line_plane(camera_position, camera_point_b, origin, camera_vector * -1)
    if obj is None:
        world_matrix = mathutils.Matrix.Identity(4)
    else:
        world_matrix = obj.matrix_world.to_quaternion()

    # Axis constraint
    if len(snapping) == 1:
        if snapping == 'X':
            point2 = origin + world_matrix @ Vector((1, 0, 0))
        elif snapping == 'Y':
            point2 = origin + world_matrix @ Vector((0, 1, 0))
        else:
            point2 = origin + world_matrix @ Vector((0, 0, 1))
        return mathutils.geometry.intersect_line_line(camera_position, camera_point_b, origin, point2)[1]

    # Planar constraint
    if len(snapping) == 2:
        if snapping == 'XY':
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 1000, 0))
        elif snapping == 'YZ':
            point2 = origin + world_matrix @ Vector((0, 1000, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))
        else:
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))

        normal = mathutils.geometry.normal(origin, point2, point3)
        new_target = mathutils.geometry.intersect_line_plane(camera_position, camera_point_b, origin, normal, False)
        return new_target


def display_keymap(kmi, layout):
    """
    Display keymap in UILayout
    """
    layout.emboss = 'NORMAL'
    if kmi is None:
        return
    map_type = kmi.map_type

    row = layout.row()
    row.prop(kmi, "active", text="", emboss=False)
    row.alignment = 'EXPAND'
    label_container = row.row().row()
    label_container.alignment = 'LEFT'
    label_container.emboss = 'NONE'
    label_container.enabled = False
    label_container.operator(kmi.idname, text=kmi.name)

    split = row.split()
    row = split.row()
    row.alignment = 'RIGHT'
    insert_prop_with_width(kmi, "map_type", row, text="", size=5)
    if map_type == 'KEYBOARD':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'MOUSE':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'NDOF':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'TWEAK':
        subrow = row.row()
        insert_prop_with_width(kmi, "type", subrow, text="", size=4)
        insert_prop_with_width(kmi, "value", subrow, text="", size=4)
    elif map_type == 'TIMER':
        insert_prop_with_width(kmi, "type", row, text="", size=8)
    else:
        insert_prop_with_width(kmi, "type", row, text="", size=8)


def insert_prop_with_width(property_object, property_name, layout, align='CENTER', text=None, icon='NONE',
                           expand=False, slider=False, icon_only=False, toggle=False, size=5, enabled=True,
                           full_event=False):
    """
    Insert UILayout prop with a fixed width
    """
    ui_container = layout.row()
    ui_container.alignment = align
    ui_container.ui_units_x = size
    if not enabled:
        ui_container.enabled = False
    ui_container.prop(property_object, property_name, icon=icon, toggle=toggle, text=text, expand=expand, slider=slider,
                      icon_only=icon_only, full_event=full_event)


def insert_ui_hotkey(container, key, description, control=False, shift=False):
    """
    Insert UI hotkey information: KeyMap icons + description
    """
    line = container.row(align=True)
    container_description = line.split(factor=0.39)
    row = container_description.row(align=True)
    row.alignment = 'RIGHT'
    if control:
        row.label(text="", icon="EVENT_CTRL")
    if shift:
        row.label(text="", icon="EVENT_SHIFT")
    row.label(text="", icon=key)
    container_description.label(text=description)


def flatten(nested_list):
    """
    Flattens nested lists
    """
    return [item for sublist in nested_list for item in sublist]


def translate_curvepoints_worldspace(obj, backup_data, translation):
    """
    Apply translation to curve points
    """
    curve_data = obj.data
    for (curve_index, index, co, bezier, left, right) in backup_data:
        if bezier:
            curve_data.splines[curve_index].bezier_points[index].co = translation @ co.copy()
            curve_data.splines[curve_index].bezier_points[index].handle_left = translation @ left.copy()
            curve_data.splines[curve_index].bezier_points[index].handle_right = translation @ right.copy()
        else:
            original_point = Vector((co[0], co[1], co[2]))
            target_position = translation @ original_point
            curve_data.splines[curve_index].points[index].co = (target_position[0],
                                                                target_position[1],
                                                                target_position[2],
                                                                0)
    pass
