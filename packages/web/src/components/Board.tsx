"use client";

import { useState, useMemo } from "react";
import { DndContext, DragOverlay, pointerWithin, type DragStartEvent, type DragEndEvent } from "@dnd-kit/core";
import { useProjects, useTasks, moveTask } from "@/lib/hooks";
import type { Task } from "@/lib/supabase";
import Column from "./Column";
import StatsBar from "./StatsBar";
import AddTaskDialog from "./AddTaskDialog";
import TaskCard from "./TaskCard";

export default function Board() {
  const projects = useProjects();
  const { tasks } = useTasks();
  const [showAdd, setShowAdd] = useState(false);
  const [search, setSearch] = useState("");
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  // Group tasks by project, inbox first
  const columns = useMemo(() => {
    const byProject = new Map<string, Task[]>();
    for (const p of projects) {
      byProject.set(p.id, []);
    }
    for (const t of tasks) {
      const list = byProject.get(t.project_id) || [];
      list.push(t);
      byProject.set(t.project_id, list);
    }

    // Filter by search
    if (search) {
      const q = search.toLowerCase();
      for (const [pid, list] of byProject) {
        byProject.set(
          pid,
          list.filter((t) => t.description.toLowerCase().includes(q))
        );
      }
    }

    // Sort: inbox first, then by position
    const sorted = [...projects].sort((a, b) => {
      if (a.slug === "inbox") return -1;
      if (b.slug === "inbox") return 1;
      return a.position - b.position;
    });

    return sorted.map((p) => ({
      project: p,
      tasks: byProject.get(p.id) || [],
    }));
  }, [projects, tasks, search]);

  const handleDragStart = (event: DragStartEvent) => {
    const task = tasks.find((t) => t.id === event.active.id);
    if (task) setActiveTask(task);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveTask(null);
    const { active, over } = event;
    if (!over) return;

    const taskId = active.id as string;
    const newProjectId = over.id as string;
    const task = tasks.find((t) => t.id === taskId);
    if (task && task.project_id !== newProjectId) {
      moveTask(taskId, newProjectId);
    }
  };

  return (
    <DndContext
      collisionDetection={pointerWithin}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="min-h-screen bg-gray-100 p-4 max-w-[100vw] overflow-x-hidden">
        <header className="flex justify-between items-center mb-3 flex-wrap gap-2">
          <h1 className="text-xl font-semibold">ToDo Schwesti</h1>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400 w-40"
            />
            <button
              onClick={() => setShowAdd(true)}
              className="bg-gray-900 text-white text-sm px-3 py-1.5 rounded-lg hover:bg-gray-800 transition-colors"
            >
              + Add
            </button>
          </div>
        </header>

        <StatsBar tasks={tasks} />

        <div className="flex gap-3.5 overflow-x-auto items-start pb-4 max-md:flex-col max-md:overflow-x-visible">
          {columns.map(({ project, tasks: projectTasks }) => {
            const hasContent = projectTasks.some((t) => !t.done) || projectTasks.some((t) => t.done);
            if (!hasContent && project.slug !== "inbox") return null;
            return <Column key={project.id} project={project} tasks={projectTasks} />;
          })}
        </div>

        {showAdd && <AddTaskDialog projects={projects} onClose={() => setShowAdd(false)} />}
      </div>

      <DragOverlay>
        {activeTask ? <TaskCard task={activeTask} isDragOverlay /> : null}
      </DragOverlay>
    </DndContext>
  );
}
