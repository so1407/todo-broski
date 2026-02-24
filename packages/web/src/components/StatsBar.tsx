"use client";

import type { Task } from "@/lib/supabase";

function isOverdue(task: Task): boolean {
  if (!task.due || task.done) return false;
  return task.due < new Date().toISOString().split("T")[0];
}

function isDueSoon(task: Task): boolean {
  if (!task.due || task.done) return false;
  const today = new Date();
  const due = new Date(task.due + "T00:00:00");
  const diff = Math.ceil((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
  return diff >= 0 && diff <= 3;
}

export default function StatsBar({ tasks }: { tasks: Task[] }) {
  const open = tasks.filter((t) => !t.done);
  const overdue = open.filter(isOverdue).length;
  const urgent = open.filter((t) => t.urgent && !isOverdue(t)).length;
  const dueSoon = open.filter((t) => isDueSoon(t) && !isOverdue(t)).length;

  return (
    <div className="flex flex-wrap gap-4 mb-4 text-xs text-gray-500">
      {overdue > 0 && (
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          {overdue} overdue
        </span>
      )}
      {urgent > 0 && (
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-orange-400" />
          {urgent} urgent
        </span>
      )}
      {dueSoon > 0 && (
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          {dueSoon} due soon
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-gray-400" />
        {open.length} total
      </span>
    </div>
  );
}
