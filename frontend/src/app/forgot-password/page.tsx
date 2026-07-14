"use client";
import React, { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import api from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSuccess("If an account with that email exists, we've sent a password reset link.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-surface">
      <div className="w-full max-w-sm text-center">
        <div className="w-10 h-10 rounded-pill bg-apple-blue flex items-center justify-center mx-auto mb-4">
          <span className="text-white font-bold text-[20px]">A</span>
        </div>
        <h1 className="text-[34px] font-semibold text-text-primary tracking-tight mb-2">Reset password</h1>
        <p className="text-[17px] text-text-secondary mb-8">Enter your email to receive a reset link</p>
        <form onSubmit={handleSubmit} className="space-y-5 text-left">
          {error && <div className="p-3 rounded-lg bg-apple-red/10 border border-apple-red/20 text-[15px] text-apple-red">{error}</div>}
          {success && <div className="p-3 rounded-lg bg-apple-green/10 border border-apple-green/20 text-[15px] text-apple-green">{success}</div>}
          <Input label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
          <Button type="submit" loading={loading} className="w-full">Send Reset Link</Button>
        </form>
        <Link href="/auth/login" className="text-apple-blue-on-dark font-medium hover:underline text-[15px] inline-block mt-6">Back to Sign In</Link>
      </div>
    </div>
  );
}
