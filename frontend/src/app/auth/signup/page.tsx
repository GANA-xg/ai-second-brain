"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Brain } from "lucide-react";

export default function SignupPage() {
  const { signup } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      await signup(email, fullName, password);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
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
          <h1 className="text-display-xl text-ink">Create account</h1>
          <p className="text-body-md text-ink-muted mt-2">Start your Second Brain journey</p>
        </div>

        <div className="bg-canvas rounded-xl p-8 shadow-card border border-border">
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-sm bg-rausch-light border border-rausch/20 text-body-sm text-error animate-fade-in">
                {error}
              </div>
            )}
            <Input
              label="Full Name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              required
            />
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Create a password (8+ characters)"
              required
            />
            <Input
              label="Confirm Password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirm your password"
              required
            />
            <Button type="submit" loading={loading} className="w-full">
              Create Account
            </Button>
          </form>
        </div>

        <p className="text-center text-body-md text-ink-muted mt-6">
          Already have an account?{" "}
          <Link
            href="/auth/login"
            className="text-rausch font-medium hover:underline"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
