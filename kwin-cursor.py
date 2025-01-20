import obspython as obs
import subprocess

# Required by advss helpers
import threading
from typing import NamedTuple

MAX_INT = 2**31 - 1

def get_condition_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_int(
        props, "kwin_cursor_min_x", "Min X:", 0, MAX_INT, 1
    )
    obs.obs_properties_add_int(
        props, "kwin_cursor_min_y", "Min Y:", 0, MAX_INT, 1
    )
    obs.obs_properties_add_int(
        props, "kwin_cursor_max_x", "Max X:", 0, MAX_INT, 1
    )
    obs.obs_properties_add_int(
        props, "kwin_cursor_max_y", "Max Y:", 0, MAX_INT, 1
    )
    return props


def get_condition_defaults():
    default_settings = obs.obs_data_create()
    obs.obs_data_set_default_int(default_settings, "kwin_cursor_min_x", 0)
    obs.obs_data_set_default_int(default_settings, "kwin_cursor_min_y", 0)
    obs.obs_data_set_default_int(default_settings, "kwin_cursor_max_x", 0)
    obs.obs_data_set_default_int(default_settings, "kwin_cursor_max_y", 0)
    return default_settings


def cursor_condition(data, instance_id):
    pos_str = subprocess.check_output(["kdotool", "getmouselocation"], text=True)
    try:
        fields = pos_str.split(" ")
        x = int(fields[0].split(":")[1])
        y = int(fields[1].split(":")[1])
    except IndexError:
        return False

    min_x = obs.obs_data_get_double(data, "kwin_cursor_min_x")
    max_x = obs.obs_data_get_double(data, "kwin_cursor_max_x")
    min_y = obs.obs_data_get_double(data, "kwin_cursor_min_y")
    max_y = obs.obs_data_get_double(data, "kwin_cursor_max_y")
    return x >= min_x and x <= max_x and y >= min_y and y <= max_y


###############################################################################


def script_load(settings):
    advss_register_condition(
        "KWin Cursor",
        cursor_condition,
        get_condition_properties,
        get_condition_defaults(),
    )


def script_unload():
    advss_deregister_condition("KWin Cursor")


###############################################################################

# Advanced Scene Switcher helper functions below:
# Usually you should not have to modify this code.
# Simply copy paste it into your scripts.


###############################################################################
# Actions
###############################################################################


# The advss_register_action() function is used to register custom actions
# It takes the following arguments:
# 1. The name of the new action type.
# 2. The function callback which should run when the action is executed.
# 3. The optional function callback which return the properties to display the
#    settings of this action type.
# 4. The optional default_settings pointer used to set the default settings of
#    newly created actions.
#    The pointer must not be freed within this script.
# 5. The optional list of macro properties associated with this action type.
#    You can set values using advss_set_temp_var_value().


def advss_register_action(
    name,
    callback,
    get_properties=None,
    default_settings=None,
    macro_properties=None,
):
    advss_register_segment_type(
        True, name, callback, get_properties, default_settings, macro_properties
    )


def advss_deregister_action(name):
    advss_deregister_segment(True, name)


###############################################################################
# Conditions
###############################################################################


# The advss_register_condition() function is used to register custom conditions
# It takes the following arguments:
# 1. The name of the new condition type.
# 2. The function callback which should run when the condition is executed.
# 3. The optional function callback which return the properties to display the
#    settings of this condition type.
# 4. The optional default_settings pointer used to set the default settings of
#    newly created condition.
#    The pointer must not be freed within this script.
# 5. The optional list of macro properties associated with this condition type.
#    You can set values using advss_set_temp_var_value().
def advss_register_condition(
    name,
    callback,
    get_properties=None,
    default_settings=None,
    macro_properties=None,
):
    advss_register_segment_type(
        False, name, callback, get_properties, default_settings, macro_properties
    )


def advss_deregister_condition(name):
    advss_deregister_segment(False, name)


###############################################################################
# (De)register helpers
###############################################################################


def advss_register_segment_type(
    is_action, name, callback, get_properties, default_settings, macro_properties
):
    proc_handler = obs.obs_get_proc_handler()
    data = obs.calldata_create()

    obs.calldata_set_string(data, "name", name)
    obs.calldata_set_ptr(data, "default_settings", default_settings)

    register_proc = (
        "advss_register_script_action"
        if is_action
        else "advss_register_script_condition"
    )
    obs.proc_handler_call(proc_handler, register_proc, data)

    success = obs.calldata_bool(data, "success")
    if success is False:
        segment_type = "action" if is_action else "condition"
        log_msg = f'failed to register custom {segment_type} "{name}"'
        obs.script_log(obs.LOG_WARNING, log_msg)
        obs.calldata_destroy(data)
        return

    # Run in separate thread to avoid blocking main OBS signal handler.
    # Operation completion will be indicated via signal completion_signal_name.
    def run_helper(data):
        completion_signal_name = obs.calldata_string(data, "completion_signal_name")
        completion_id = obs.calldata_int(data, "completion_id")
        instance_id = obs.calldata_int(data, "instance_id")

        def thread_func(settings):
            settings = obs.obs_data_create_from_json(
                obs.calldata_string(data, "settings")
            )
            callback_result = callback(settings, instance_id)
            if is_action:
                callback_result = True

            reply_data = obs.calldata_create()
            obs.calldata_set_int(reply_data, "completion_id", completion_id)
            obs.calldata_set_bool(reply_data, "result", callback_result)
            signal_handler = obs.obs_get_signal_handler()
            obs.signal_handler_signal(
                signal_handler, completion_signal_name, reply_data
            )
            obs.obs_data_release(settings)
            obs.calldata_destroy(reply_data)

        threading.Thread(target=thread_func, args={data}).start()

    def properties_helper(data):
        if get_properties is not None:
            properties = get_properties()
        else:
            properties = None
        obs.calldata_set_ptr(data, "properties", properties)

    # Helper to register the macro properties every time a new instance of the
    # macro segment is created.
    def register_temp_vars_helper(data):
        id = obs.calldata_int(data, "instance_id")
        proc_handler = obs.obs_get_proc_handler()
        data = obs.calldata_create()
        for prop in macro_properties:
            obs.calldata_set_string(data, "temp_var_id", prop.id)
            obs.calldata_set_string(data, "temp_var_name", prop.name)
            obs.calldata_set_string(data, "temp_var_help", prop.description)
            obs.calldata_set_int(data, "instance_id", id)

            obs.proc_handler_call(proc_handler, "advss_register_temp_var", data)

            success = obs.calldata_bool(data, "success")
            if success is False:
                segment_type = "action" if is_action else "condition"
                log_msg = f'failed to register macro property {prop.id} for {segment_type} "{name}"'
                obs.script_log(obs.LOG_WARNING, log_msg)
        obs.calldata_destroy(data)

    trigger_signal_name = obs.calldata_string(data, "trigger_signal_name")
    property_signal_name = obs.calldata_string(data, "properties_signal_name")
    new_instance_signal_name = obs.calldata_string(data, "new_instance_signal_name")

    signal_handler = obs.obs_get_signal_handler()
    obs.signal_handler_connect(signal_handler, trigger_signal_name, run_helper)
    obs.signal_handler_connect(signal_handler, property_signal_name, properties_helper)
    if isinstance(macro_properties, list):
        obs.signal_handler_connect(
            signal_handler, new_instance_signal_name, register_temp_vars_helper
        )
    obs.calldata_destroy(data)


def advss_deregister_segment(is_action, name):
    proc_handler = obs.obs_get_proc_handler()
    data = obs.calldata_create()

    obs.calldata_set_string(data, "name", name)

    deregister_proc = (
        "advss_deregister_script_action"
        if is_action
        else "advss_deregister_script_condition"
    )

    obs.proc_handler_call(proc_handler, deregister_proc, data)

    success = obs.calldata_bool(data, "success")
    if success is False:
        segment_type = "action" if is_action else "condition"
        log_msg = f'failed to deregister custom {segment_type} "{name}"'
        obs.script_log(obs.LOG_WARNING, log_msg)

    obs.calldata_destroy(data)


###############################################################################
# Macro properties (temporary variables)
###############################################################################


class MacroProperty(NamedTuple):
    id: str  # Internal identifier used by advss_set_temp_var_value()
    name: str  # User facing name
    description: str  # User facing description


def advss_set_temp_var_value(temp_var_id, value, instance_id):
    proc_handler = obs.obs_get_proc_handler()
    data = obs.calldata_create()

    obs.calldata_set_string(data, "temp_var_id", str(temp_var_id))
    obs.calldata_set_string(data, "value", str(value))
    obs.calldata_set_int(data, "instance_id", int(instance_id))
    obs.proc_handler_call(proc_handler, "advss_set_temp_var_value", data)

    success = obs.calldata_bool(data, "success")
    if success is False:
        obs.script_log(
            obs.LOG_WARNING, f'failed to set value for macro property "{temp_var_id}"'
        )

    obs.calldata_destroy(data)


###############################################################################
# Variables
###############################################################################


# The advss_get_variable_value() function can be used to query the value of a
# variable with a given name.
# None is returned in case the variable does not exist.
def advss_get_variable_value(name):
    proc_handler = obs.obs_get_proc_handler()
    data = obs.calldata_create()

    obs.calldata_set_string(data, "name", name)
    obs.proc_handler_call(proc_handler, "advss_get_variable_value", data)

    success = obs.calldata_bool(data, "success")
    if success is False:
        obs.script_log(obs.LOG_WARNING, f'failed to get value for variable "{name}"')
        obs.calldata_destroy(data)
        return None

    value = obs.calldata_string(data, "value")

    obs.calldata_destroy(data)
    return value


# The advss_set_variable_value() function can be used to set the value of a
# variable with a given name.
# True is returned if the operation was successful.
def advss_set_variable_value(name, value):
    proc_handler = obs.obs_get_proc_handler()
    data = obs.calldata_create()

    obs.calldata_set_string(data, "name", name)
    obs.calldata_set_string(data, "value", value)
    obs.proc_handler_call(proc_handler, "advss_set_variable_value", data)

    success = obs.calldata_bool(data, "success")
    if success is False:
        obs.script_log(obs.LOG_WARNING, f'failed to set value for variable "{name}"')

    obs.calldata_destroy(data)
    return success
