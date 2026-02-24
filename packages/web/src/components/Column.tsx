"use client";

import { useState } from "react";
import type { Task, Project } from "@/lib/supabase";
import TaskCard from "./TaskCard";

export default function Column({
  project,
  tasks,
}: {
  project: Project;
  tasks: Task[];
}) {
  const [showDone, setShowDone] = useState(false);

  const active = tasks.filter((t) => !t.done);
  const done = tasks.filter((t) => t.done);

  return (
    <div className="bg-white rounded-xl min-w-[280px] max-w-[320px] flex-shrink-0 shadow-sm md:max-w-[320px] max-md:min-w-0 max-md:max-w-none max-md:w-full">
      <div className="px-3.5 pt-3 pb-2.5 font-semibold text-sm border-b border-gray-100 flex justify-between items-center sticky top-0 bg-white rounded-t-xl z-[1]">
        {project.name}
        <span className="bg-gray-200 text-gray-600 text-[11px] px-2 py-0.5 rounded-xl font-medium">
          {active.length}
        </span>
      </div>
      <div className="p-1.5">
        {active.map((t) => (
          <TaskCard key={t.id} task={t} />
        ))}
        {active.length === 0 && (
          <div className="text-xs text-gray-400 text-center py-4">No active tasks</div>
        )}
      </div>
      {done.length > 0 && (
        <div className="border-t border-gray-100 mt-1.5 pt-1">
          <button
            className="text-xs text-gray-400 cursor-pointer px-3 py-2 hover:text-gray-600 select-none"
            onClick={() => setShowDone(!showDone)}
          >
            {done.length} completed {showDone ? "▾" : "▸"}
          </button>
          {showDone && (
            <div className="px-1.5 pb-2">
              {done.map((t) => (
                <TaskCard key={t.id} task={t} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
