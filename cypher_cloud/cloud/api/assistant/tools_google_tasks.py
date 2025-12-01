# cloud/api/assistant/tools_google_tasks.py
from googleapiclient.discovery import build
from cloud.api.assistant.google_auth import get_google_creds


def _get_tasks_service():
    creds = get_google_creds()
    return build("tasks", "v1", credentials=creds)


async def google_tasks_tool(args: dict, ctx: dict) -> dict:
    service = _get_tasks_service()

    action = args.get("action", "add")
    text = args.get("text")
    task_id = args.get("id")

    # Default list
    tasklist = service.tasklists().list().execute()["items"][0]["id"]

    # ---------- ADD ----------
    if action == "add":
        if not text:
            return {"status": "error", "message": "No task description provided."}

        task = service.tasks().insert(
            tasklist=tasklist,
            body={"title": text}
        ).execute()

        return {"status": "ok", "task": task["title"]}

    # ---------- LIST ----------
    if action == "list":
        tasks = service.tasks().list(tasklist=tasklist).execute().get("items", [])
        return {
            "status": "ok",
            "tasks": [{"id": t["id"], "title": t["title"]} for t in tasks]
        }

    # ---------- COMPLETE ----------
    if action == "complete":
        service.tasks().update(
            tasklist=tasklist,
            task=task_id,
            body={"status": "completed"}
        ).execute()

        return {"status": "ok", "completed": task_id}

    # ---------- CLEAR ----------
    if action == "clear":
        tasks = service.tasks().list(tasklist=tasklist).execute().get("items", [])
        for t in tasks:
            service.tasks().delete(tasklist=tasklist, task=t["id"]).execute()
        return {"status": "ok", "cleared": len(tasks)}

    return {"status": "error", "message": f"Unknown task action: {action}"}
