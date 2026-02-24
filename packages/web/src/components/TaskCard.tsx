"use client";

import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import type { Task } from "@/lib/supabase";
import { completeTask, uncompleteTask, updateTask, deleteTask } from "@/lib/hooks";

function getTaskStatus(task: Task): "overdue" | "urgent" | "due-soon" | "normal" {
  if (!task.done && task.due && task.due < new Date().toISOString().split("T")[0]) return "overdue";
  if (!task.done && task.urgent) return "urgent";
  if (!task.done && task.due) {
    const today = new Date();
    const due = new Date(task.due + "T00:00:00");
    const diff = Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    if (diff >= 0 && diff <= 3) return "due-soon";
  }
  return "normal";
}

const statusStyles = {
  overdue: "border-l-red-500 bg-red-50",
  urgent: "border-l-orange-400 bg-orange-50",
  "due-soon": "border-l-blue-500 bg-blue-50",
  normal: "border-l-gray-300 bg-gray-50",
};

const checkboxStyles = {
  overdue: "border-red-400",
  urgent: "border-orange-300",
  "due-soon": "border-blue-400",
  normal: "border-gray-300",
};

export default function TaskCard({ task, isDragOverlay }: { task: Task; isDragOverlay?: boolean }) {
  const [completing, setCompleting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(task.description);
  const status = getTaskStatus(task);

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    disabled: task.done || editing,
  });

  const style = transform && !isDragOverlay
    ? { transform: CSS.Translate.toString(transform) }
    : undefined;

  const handleComplete = async () => {
    setCompleting(true);
    if (task.done) {
      await uncompleteTask(task.id);
    } else {
      await completeTask(task.id);
    }
  };

  const handleSaveEdit = async () => {
    if (editText.trim() && editText !== task.description) {
      await updateTask(task.id, { description: editText.trim() });
    }
    setEditing(false);
  };

  const handleDelete = async () => {
    await deleteTask(task.id);
  };

  if (task.done) {
    return (
      <div className="px-3 py-1.5 my-1 text-xs text-gray-400 line-through rounded-md">
        {task.description}
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-start gap-2.5 p-2.5 px-3 my-1.5 rounded-lg border-l-[3px] text-sm leading-relaxed transition-all ${statusStyles[status]} ${completing ? "opacity-40 scale-[0.97] line-through text-gray-400" : ""} ${isDragging && !isDragOverlay ? "opacity-30" : ""} ${isDragOverlay ? "shadow-lg rotate-1" : ""}`}
    >
      {/* Drag handle */}
      <button
        {...listeners}
        {...attributes}
        className="flex-shrink-0 text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing mt-0.5 text-xs select-none touch-none"
        title="Drag to move"
      >
        ⠿
      </button>
      <button
        onClick={handleComplete}
        className={`flex-shrink-0 w-[22px] h-[22px] rounded-full border-2 ${checkboxStyles[status]} bg-transparent cursor-pointer mt-0.5 flex items-center justify-center text-xs text-transparent hover:border-green-500 hover:bg-green-50 hover:text-green-500 transition-all`}
        title="Mark done"
      >
        ✓
      </button>
      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            className="w-full text-sm font-medium bg-white border border-gray-200 rounded px-2 py-1 focus:outline-none focus:border-blue-400"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onBlur={handleSaveEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSaveEdit();
              if (e.key === "Escape") {
                setEditText(task.description);
                setEditing(false);
              }
            }}
            autoFocus
          />
        ) : (
          <div
            className="font-medium cursor-pointer"
            onClick={() => {
              setEditText(task.description);
              setEditing(true);
            }}
          >
            {task.description}
          </div>
        )}
        <div className="flex gap-1.5 mt-1 flex-wrap text-[11px] text-gray-500">
          {status === "overdue" && (
            <span className="bg-red-100 text-red-700 px-1.5 py-px rounded">overdue</span>
          )}
          {task.urgent && status !== "overdue" && (
            <span className="bg-orange-100 text-orange-700 px-1.5 py-px rounded">urgent</span>
          )}
          {task.due && <span className="bg-gray-100 px-1.5 py-px rounded">{task.due}</span>}
          {task.effort && <span className="bg-gray-100 px-1.5 py-px rounded">{task.effort}</span>}
        </div>
      </div>
      <button
        onClick={handleDelete}
        className="flex-shrink-0 text-gray-300 hover:text-red-400 text-xs mt-0.5 transition-colors"
        title="Delete task"
      >
        ×
      </button>
    </div>
  );
}
