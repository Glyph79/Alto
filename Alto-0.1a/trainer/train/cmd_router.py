"""Router that assembles the COMMANDS dictionary from all command modules."""
from .commands.model_cmds import (
    cmd_list_models, cmd_create_model, cmd_get_model, cmd_update_model,
    cmd_delete_model, cmd_rename_model, cmd_get_model_db_path
)
from .commands.group_cmds import (
    cmd_add_group, cmd_update_group, cmd_delete_group,
    cmd_add_question, cmd_update_question, cmd_delete_question,
    cmd_add_answer, cmd_update_answer, cmd_delete_answer,
    cmd_get_followups, cmd_save_followups, cmd_get_node_details,
    cmd_get_group_summaries, cmd_get_group_full   # <-- added
)
from .commands.section_cmds import (
    cmd_add_section, cmd_rename_section, cmd_delete_section
)
from .commands.import_export import cmd_import_db
from .commands.topic_cmds import (
    cmd_get_topics, cmd_add_topic, cmd_rename_topic, cmd_delete_topic
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
    "add-question":     cmd_add_question,
    "update-question":  cmd_update_question,
    "delete-question":  cmd_delete_question,
    "add-answer":       cmd_add_answer,
    "update-answer":    cmd_update_answer,
    "delete-answer":    cmd_delete_answer,
    "get-followups":    cmd_get_followups,
    "save-followups":   cmd_save_followups,
    "get-node-details": cmd_get_node_details,
    "add-section":      cmd_add_section,
    "rename-section":   cmd_rename_section,
    "delete-section":   cmd_delete_section,
    "import-db":        cmd_import_db,
    # New topic commands
    "get-topics":       cmd_get_topics,
    "add-topic":        cmd_add_topic,
    "rename-topic":     cmd_rename_topic,
    "delete-topic":     cmd_delete_topic,
    # New lightweight group commands
    "get-group-summaries": cmd_get_group_summaries,
    "get-group-full":      cmd_get_group_full,
}