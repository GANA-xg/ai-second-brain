"use client";
import React, { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Brain } from "lucide-react";
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
    <div className="min-h-screen flex items-center justify-center px-6 bg-canvas-soft">
      <div className="w-full max-w-[400px] animate-fade-in-up">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-lg bg-rausch flex items-center justify-center mx-auto mb-5">
            <Brain className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-display-xl text-ink mb-2">Reset password</h1>
          <p className="text-body-md text-ink-muted">Enter your email to receive a reset link</p>
        </div>

        <div className="bg-canvas rounded-xl p-8 shadow-card border border-border">
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-sm bg-rausch-light border border-rausch/20 text-body-sm text-error animate-fade-in">
                {error}
              </div>
            )}
            {success && (
              <div className="p-3 rounded-sm bg-success-light border border-success/20 text-body-sm text-success animate-fade-in">
                {success}
              </div>
            )}
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
            <Button type="submit" loading={loading} className="w-full">
              Send Reset Link
            </Button>
          </form>
        </div>

        <p className="text-center mt-6">
          <Link href="/auth/login" className="text-rausch font-medium hover:underline text-body-md">
            Back to Sign In
          </Link>
        </p>
      </div>
    </div>
  );
}
