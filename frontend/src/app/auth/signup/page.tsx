"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
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
      await signup(email, fullName, password);
      setSuccess("Account created! Redirecting...");
      setTimeout(() => router.push("/dashboard"), 800);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
          <h1 className="text-[34px] font-semibold text-text-primary tracking-tight">Create account</h1>
          <p className="text-[17px] text-text-secondary mt-2">Start your Second Brain journey</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          {error && <div className="p-3 rounded-lg bg-apple-red/10 border border-apple-red/20 text-[15px] text-apple-red">{error}</div>}
          {success && <div className="p-3 rounded-lg bg-apple-green/10 border border-apple-green/20 text-[15px] text-apple-green">{success}</div>}
          <Input label="Full Name" type="text" value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Your name" required />
          <Input label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
          <Input label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Create a password" required />
          <Input label="Confirm Password" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Confirm your password" required />
          <Button type="submit" loading={loading} className="w-full">Create Account</Button>
        </form>
        <p className="text-center text-[15px] text-text-secondary mt-6">
          Already have an account?{" "}
          <Link href="/auth/login" className="text-apple-blue-on-dark font-medium hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
