"""Router that assembles the COMMANDS dictionary from all command modules."""
from train.models.commands import (
    cmd_list_models, cmd_create_model, cmd_get_model, cmd_update_model,
    cmd_delete_model, cmd_rename_model, cmd_get_model_db_path
)
from train.models.utils import cmd_import_db
from train.groups.commands import (
    cmd_add_group, cmd_update_group, cmd_delete_group,
    cmd_get_followups, cmd_save_followups, cmd_get_node_details,
    cmd_get_group_summaries, cmd_get_group_full
)
from train.sections.commands import (
    cmd_add_section, cmd_rename_section, cmd_delete_section
)
from train.topics.commands import (
    cmd_get_topics, cmd_add_topic, cmd_rename_topic, cmd_delete_topic,
    cmd_get_topic_groups
)
from train.variants.commands import (
    cmd_get_variants, cmd_add_variant, cmd_update_variant, cmd_delete_variant
)

COMMANDS = {
    "list-models":      cmd_list_models,
    "create-model":     cmd_create_model,
    "get-model":        cmd_get_model,
    "update-model":     cmd_update_model,
    "delete-model":     cmd_delete_model,
    "rename-model":     cmd_rename_model,
    "get-model-db-path": cmd_get_model_db_path,
    "import-db":        cmd_import_db,
    "add-group":        cmd_add_group,
    "update-group":     cmd_update_group,
    "delete-group":     cmd_delete_group,
    "get-followups":    cmd_get_followups,
    "save-followups":   cmd_save_followups,
    "get-node-details": cmd_get_node_details,
    "get-group-summaries": cmd_get_group_summaries,
    "get-group-full":      cmd_get_group_full,
    "add-section":      cmd_add_section,
    "rename-section":   cmd_rename_section,
    "delete-section":   cmd_delete_section,
    "get-topics":       cmd_get_topics,
    "add-topic":        cmd_add_topic,
    "rename-topic":     cmd_rename_topic,
    "delete-topic":     cmd_delete_topic,
    "get-topic-groups": cmd_get_topic_groups,
    "get-variants":     cmd_get_variants,
    "add-variant":      cmd_add_variant,
    "update-variant":   cmd_update_variant,
    "delete-variant":   cmd_delete_variant,
}