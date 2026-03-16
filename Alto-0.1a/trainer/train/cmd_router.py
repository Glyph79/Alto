"""Router that assembles the COMMANDS dictionary from all command modules."""
from .commands.model_cmds import (
    cmd_list_models, cmd_create_model, cmd_get_model, cmd_update_model,
    cmd_delete_model, cmd_rename_model, cmd_get_model_db_path
)
from .commands.group_cmds import (
    cmd_add_group, cmd_update_group, cmd_delete_group,
    cmd_get_followups, cmd_save_followups, cmd_get_node_details,
    cmd_get_group_summaries, cmd_get_group_full
)
from .commands.section_cmds import (
    cmd_add_section, cmd_rename_section, cmd_delete_section
)
from .commands.import_export import cmd_import_db
from .commands.topic_cmds import (
    cmd_get_topics, cmd_add_topic, cmd_rename_topic, cmd_delete_topic,
    cmd_get_topic_groups
)
from .commands.variant_cmds import (
    cmd_get_variants, cmd_add_variant, cmd_update_variant, cmd_delete_variant
)
from .commands.route_cmds import (   # <-- new
    cmd_get_route_summaries, cmd_get_route_full,
    cmd_add_route, cmd_update_route, cmd_delete_route
)

COMMANDS = {
    "list-models":      cmd_list_models,
    "create-model":     cmd_create_model,
    "get-model":        cmd_get_model,
    "update-model":     cmd_update_model,
    "delete-model":     cmd_delete_model,
    "rename-model":     cmd_rename_model,
    "get-model-db-path": cmd_get_model_db_path,
    "add-group":        cmd_add_group,
    "update-group":     cmd_update_group,
    "delete-group":     cmd_delete_group,
    "get-followups":    cmd_get_followups,
    "save-followups":   cmd_save_followups,
    "get-node-details": cmd_get_node_details,
    "add-section":      cmd_add_section,
    "rename-section":   cmd_rename_section,
    "delete-section":   cmd_delete_section,
    "import-db":        cmd_import_db,
    "get-topics":       cmd_get_topics,
    "add-topic":        cmd_add_topic,
    "rename-topic":     cmd_rename_topic,
    "delete-topic":     cmd_delete_topic,
    "get-topic-groups": cmd_get_topic_groups,
    "get-group-summaries": cmd_get_group_summaries,
    "get-group-full":      cmd_get_group_full,
    "get-variants":     cmd_get_variants,
    "add-variant":      cmd_add_variant,
    "update-variant":   cmd_update_variant,
    "delete-variant":   cmd_delete_variant,
    # New route commands
    "get-route-summaries": cmd_get_route_summaries,
    "get-route-full":      cmd_get_route_full,
    "add-route":           cmd_add_route,
    "update-route":        cmd_update_route,
    "delete-route":        cmd_delete_route,
}