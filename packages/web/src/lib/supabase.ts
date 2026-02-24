import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

export const supabase = supabaseUrl
  ? createClient(supabaseUrl, supabaseKey)
  : (null as unknown as ReturnType<typeof createClient>);

export type Project = {
  id: string;
  name: string;
  slug: string;
  color: string | null;
  position: number;
  archived: boolean;
};

export type Task = {
  id: string;
  project_id: string;
  description: string;
  done: boolean;
  due: string | null;
  urgent: boolean;
  effort: string | null;
  position: number;
  priority_score: number;
  notes: string | null;
  done_date: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  // Joined
  projects?: { name: string; slug: string };
};
