"use client";
import { CheckCircle, XCircle } from "lucide-react";

interface Props {
  message: string;
  type: "error" | "success";
}

export function Toast({ message, type }: Props) {
  return (
    <div
      className={`pointer-events-auto flex items-center gap-2 px-4 py-3 rounded-xl shadow-soft border text-sm font-medium max-w-sm animate-[fadeInUp_0.25s_ease-out] ${
        type === "error"
          ? "bg-white border-rose/20 text-rose"
          : "bg-white border-success/20 text-success"
      }`}
    >
      {type === "error" ? (
        <XCircle size={16} className="shrink-0" />
      ) : (
        <CheckCircle size={16} className="shrink-0" />
      )}
      <span>{message}</span>
    </div>
  );
}
