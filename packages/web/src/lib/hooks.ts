"use client";

import { useEffect, useState, useCallback } from "react";
import { supabase, type Project, type Task } from "./supabase";

export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);

  const load = useCallback(async () => {
    const { data } = await supabase
      .from("projects")
      .select("*")
      .eq("archived", false)
      .order("position");
    if (data) setProjects(data);
  }, []);

  useEffect(() => {
    load();

    const channel = supabase
      .channel("projects-changes")
      .on("postgres_changes", { event: "*", schema: "public", table: "projects" }, () => {
        load();
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [load]);

  return projects;
}

export function useTasks() {
  const [tasks, setTasks] = useState<Task[]>([]);

  const load = useCallback(async () => {
    const { data } = await supabase
      .from("tasks")
      .select("*, projects(name, slug)")
      .order("priority_score", { ascending: false })
      .order("position");
    if (data) setTasks(data);
  }, []);

  useEffect(() => {
    load();

    const channel = supabase
      .channel("tasks-changes")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, () => {
        load();
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [load]);

  return { tasks, reload: load };
}

export async function addTask(
  description: string,
  projectId: string,
  options: { due?: string; urgent?: boolean; effort?: string } = {}
) {
  const { error } = await supabase.from("tasks").insert({
    project_id: projectId,
    description,
    due: options.due || null,
    urgent: options.urgent || false,
    effort: options.effort || null,
    source: "web",
  });
  return !error;
}

export async function completeTask(taskId: string) {
  const today = new Date().toISOString().split("T")[0];
  const { error } = await supabase
    .from("tasks")
    .update({ done: true, done_date: today })
    .eq("id", taskId);
  return !error;
}

export async function uncompleteTask(taskId: string) {
  const { error } = await supabase
    .from("tasks")
    .update({ done: false, done_date: null })
    .eq("id", taskId);
  return !error;
}

export async function updateTask(taskId: string, fields: Partial<Task>) {
  const { error } = await supabase.from("tasks").update(fields).eq("id", taskId);
  return !error;
}

export async function moveTask(taskId: string, projectId: string) {
  const { error } = await supabase
    .from("tasks")
    .update({ project_id: projectId })
    .eq("id", taskId);
  return !error;
}

export async function deleteTask(taskId: string) {
  const { error } = await supabase.from("tasks").delete().eq("id", taskId);
  return !error;
}
