"use client";
import React, { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import api from "@/lib/api";

export default function ResetPasswordPage() {
  const params = useParams();
  const token = params.token as string;
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (password !== confirmPassword) { setError("Passwords do not match"); return; }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password });
      setSuccess("Password reset successful! You can now sign in with your new password.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 bg-surface">
      <div className="w-full max-w-sm">
        <div className="text-center mb-10">
          <div className="w-10 h-10 rounded-pill bg-apple-blue flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-bold text-[20px]">A</span>
          </div>
          <h1 className="text-[34px] font-semibold text-text-primary tracking-tight">Set new password</h1>
          <p className="text-[17px] text-text-secondary mt-2">Enter your new password below</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          {error && <div className="p-3 rounded-lg bg-apple-red/10 border border-apple-red/20 text-[15px] text-apple-red">{error}</div>}
          {success && <div className="p-3 rounded-lg bg-apple-green/10 border border-apple-green/20 text-[15px] text-apple-green">{success}</div>}
          <Input label="New Password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter new password" required />
          <Input label="Confirm Password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Confirm new password" required />
          {!success && <Button type="submit" loading={loading} className="w-full">Reset Password</Button>}
        </form>
        {success && (
          <div className="mt-6 text-center">
            <Link href="/auth/login" className="text-apple-blue-on-dark font-medium hover:underline text-[15px]">Sign in with new password</Link>
          </div>
        )}
        <div className="text-center mt-6">
          <Link href="/forgot-password" className="text-apple-blue-on-dark font-medium hover:underline text-[15px]">Request new link</Link>
        </div>
      </div>
    </div>
  );
}
