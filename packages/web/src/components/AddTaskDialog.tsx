"use client";

import { useState } from "react";
import type { Project } from "@/lib/supabase";
import { addTask } from "@/lib/hooks";

export default function AddTaskDialog({
  projects,
  onClose,
}: {
  projects: Project[];
  onClose: () => void;
}) {
  const [description, setDescription] = useState("");
  const [projectId, setProjectId] = useState(projects[0]?.id || "");
  const [due, setDue] = useState("");
  const [urgent, setUrgent] = useState(false);
  const [effort, setEffort] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || !projectId) return;

    setSaving(true);
    await addTask(description.trim(), projectId, {
      due: due || undefined,
      urgent,
      effort: effort || undefined,
    });
    setSaving(false);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 space-y-4"
      >
        <h2 className="text-lg font-semibold">Add Task</h2>

        <input
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
          placeholder="Task description..."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          autoFocus
        />

        <select
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>

        <div className="flex gap-3">
          <input
            type="date"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
          <input
            className="w-24 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
            placeholder="Effort"
            value={effort}
            onChange={(e) => setEffort(e.target.value)}
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={urgent}
            onChange={(e) => setUrgent(e.target.checked)}
            className="rounded border-gray-300"
          />
          Urgent
        </label>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || !description.trim()}
            className="px-4 py-2 text-sm bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 transition-colors"
          >
            {saving ? "Adding..." : "Add Task"}
          </button>
        </div>
      </form>
    </div>
  );
}
