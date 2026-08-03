"use client";
import React, { useState, useCallback, useRef } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/components/ui/Toast";
import { memoriesApi, authApi } from "@/lib/api-client";
import type { MemoryResponse, MemoryType } from "@/lib/types";
import { useEffect, useCallback as useCallbackReact } from "react";
import { User, Bell, Shield, Palette, Trash2, Download, LogOut, Camera, Plus } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { toast } = useToast();
  const { theme, setTheme } = useTheme();

  // Profile state
  const [name, setName] = useState(user?.full_name || "");
  const [email, setEmail] = useState(user?.email || "");
  const [bio, setBio] = useState("");
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [notifications, setNotifications] = useState(true);
  const [aiModel, setAiModel] = useState("opencode");

  // Memories state
  const [memories, setMemories] = useState<MemoryResponse[]>([]);
  const [memoriesLoading, setMemoriesLoading] = useState(true);
  const [newMemoryType, setNewMemoryType] = useState<MemoryType>("FACT");
  const [newMemoryContent, setNewMemoryContent] = useState("");
  const [showAddMemory, setShowAddMemory] = useState(false);

  // Modals
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showSignOutModal, setShowSignOutModal] = useState(false);

  const fetchMemories = useCallbackReact(async () => {
    setMemoriesLoading(true);
    try {
      const res = await memoriesApi.list({ page_size: 100 });
      setMemories(res.memories);
    } catch {
    } finally {
      setMemoriesLoading(false);
    }
  }, []);

  useEffect(() => { fetchMemories(); }, [fetchMemories]);

  // Fetch real profile data from backend on mount
  useEffect(() => {
    authApi.getProfile().then((p) => {
      setName(p.full_name || "");
      setEmail(p.email || "");
      setBio(p.bio || "");
      setAvatarUrl(p.avatar_url || null);
    }).catch(() => {});
  }, []);

  // Profile handlers
  const handleAvatarChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => setAvatarUrl(ev.target?.result as string);
      reader.readAsDataURL(file);
    }
  }, []);

  const handleSaveProfile = useCallback(async () => {
    try {
      const updated = await authApi.updateProfile({
        full_name: name.trim() || undefined,
        bio: bio || undefined,
        avatar_url: avatarUrl || undefined,
      });
      toast("Profile saved successfully");
    } catch {
      toast("Failed to save profile", "error");
    }
  }, [name, bio, avatarUrl, toast]);

  // Memory handlers
  const handleAddMemory = useCallback(async () => {
    if (!newMemoryContent.trim()) return;
    try {
      await memoriesApi.create({ type: newMemoryType, content: newMemoryContent.trim() });
      setNewMemoryContent("");
      setShowAddMemory(false);
      fetchMemories();
      toast("Memory added");
    } catch {
      toast("Failed to add memory", "error");
    }
  }, [newMemoryType, newMemoryContent, fetchMemories, toast]);

  const handleDeleteMemory = useCallback(async (id: string) => {
    try {
      await memoriesApi.delete(id);
      setMemories(prev => prev.filter(m => m.id !== id));
      toast("Memory deleted");
    } catch {
      toast("Failed to delete", "error");
    }
  }, [toast]);

  const handleToggleMemory = useCallback(async (id: string, isActive: boolean) => {
    try {
      await memoriesApi.update(id, { is_active: !isActive });
      setMemories(prev => prev.map(m => m.id === id ? { ...m, is_active: !m.is_active } : m));
    } catch {
      toast("Failed to update", "error");
    }
  }, [toast]);

  const handleSignOut = useCallback(async () => {
    await logout();
    window.location.href = "/auth/login";
  }, [logout]);

  const handleExportData = useCallback(() => {
    const data = {
      profile: { name, email, bio },
      memories: memories.map(m => ({ type: m.type, content: m.content, created_at: m.created_at })),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "second-brain-export.json";
    a.click();
    URL.revokeObjectURL(url);
    toast("Data exported successfully");
  }, [name, email, bio, memories, toast]);

  return (
    <ProtectedLayout>
      <TopBar title="Settings" subtitle="Manage your account and preferences" />

      <div className="max-w-2xl space-y-8">
        {/* Profile Section */}
        <section className="animate-fade-in-up">
          <div className="flex items-center gap-2 mb-4">
            <User className="w-5 h-5 text-ink-muted" />
            <h2 className="text-title-md text-ink">Profile</h2>
          </div>
          <Card className="p-6">
            {/* Avatar */}
            <div className="flex items-center gap-4 mb-6">
              <div
                className="w-20 h-20 rounded-full bg-canvas-soft flex items-center justify-center overflow-hidden cursor-pointer border-2 border-border hover:border-rausch transition-colors relative group"
                onClick={() => fileInputRef.current?.click()}
              >
                {avatarUrl ? (
                  <img src={avatarUrl} alt="Avatar" className="w-full h-full object-cover" />
                ) : (
                  <span className="text-hero-sm text-ink-muted-soft font-medium">
                    {name ? name.charAt(0).toUpperCase() : "U"}
                  </span>
                )}
                <div className="absolute inset-0 bg-ink/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity rounded-full">
                  <Camera className="w-6 h-6 text-white" />
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleAvatarChange}
              />
              <div>
                <p className="text-body-sm text-ink font-medium">{name || "User"}</p>
                <p className="text-caption-sm text-ink-muted-soft">{email}</p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-caption-sm text-rausch font-medium mt-1 hover:underline"
                >
                  Change photo
                </button>
              </div>
            </div>

            <div className="space-y-4">
              <Input
                label="Full Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
              />
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
              <div>
                <label className="block text-caption text-ink-muted mb-1.5">Bio</label>
                <textarea
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Tell us about yourself..."
                  rows={3}
                  className="input-airbnb resize-none"
                />
              </div>
              <Button onClick={handleSaveProfile}>Save Changes</Button>
            </div>
          </Card>
        </section>

        {/* Preferences Section */}
        <section className="animate-fade-in-up" style={{ animationDelay: "100ms" } as React.CSSProperties}>
          <div className="flex items-center gap-2 mb-4">
            <Palette className="w-5 h-5 text-ink-muted" />
            <h2 className="text-title-md text-ink">Preferences</h2>
          </div>
          <Card className="p-6 space-y-5">
            {/* Theme */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-body-sm text-ink font-medium">Theme</p>
                <p className="text-caption-sm text-ink-muted-soft">Select your preferred theme</p>
              </div>
              <div className="flex gap-1 bg-canvas-soft rounded-lg p-1">
                {(["light", "dark"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t)}
                    className={`px-4 py-1.5 rounded-md text-body-sm font-medium transition-all ${
                      theme === t
                        ? "bg-canvas shadow-card text-ink"
                        : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Notifications */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-body-sm text-ink font-medium">Notifications</p>
                <p className="text-caption-sm text-ink-muted-soft">Receive email notifications</p>
              </div>
              <button
                role="switch"
                aria-checked={notifications}
                aria-label="Toggle notifications"
                onClick={() => setNotifications(!notifications)}
                className={`w-11 h-6 rounded-full transition-colors relative flex-shrink-0 ${
                  notifications ? "bg-rausch" : "bg-canvas-strong"
                }`}
              >
                  <span
                    className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-canvas shadow transition-transform`}
                    style={{ transform: `translateX(${notifications ? "20px" : "0"})` }}
                  />
              </button>
            </div>

            {/* AI Model */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-body-sm text-ink font-medium">AI Model</p>
                <p className="text-caption-sm text-ink-muted-soft">Choose your preferred AI model</p>
              </div>
              <select
                value={aiModel}
                onChange={(e) => setAiModel(e.target.value)}
                className="w-40 input-airbnb text-sm"
              >
                <option value="opencode">Opencode</option>
                <option value="openrouter">OpenRouter</option>
                <option value="grok">Grok</option>
                <option value="gemini">Gemini</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
          </Card>
        </section>

        {/* Memories Section */}
        <section className="animate-fade-in-up" style={{ animationDelay: "200ms" } as React.CSSProperties}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-ink-muted" />
              <h2 className="text-title-md text-ink">Memories</h2>
            </div>
            <button
              onClick={() => setShowAddMemory(true)}
              className="flex items-center gap-1.5 text-caption-sm text-rausch font-medium hover:underline"
            >
              <Plus className="w-4 h-4" />
              Add Memory
            </button>
          </div>
          <Card className="p-4">
            {memoriesLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-14 rounded-lg skeleton" />
                ))}
              </div>
            ) : memories.length === 0 ? (
              <p className="text-body-sm text-ink-muted text-center py-8">
                No memories yet. The AI learns from your conversations.
              </p>
            ) : (
              <div className="space-y-2">
                {memories.map((memory) => (
                  <div
                    key={memory.id}
                    className="flex items-center gap-3 p-3 rounded-lg hover:bg-canvas-soft transition-colors group"
                  >
                    <Badge variant={memory.type === "FACT" ? "info" : memory.type === "PREFERENCE" ? "danger" : "success"}>
                      {memory.type}
                    </Badge>
                    <p className="flex-1 text-body-sm text-ink truncate">{memory.content}</p>
                    <button
                      role="switch"
                      aria-checked={memory.is_active}
                      aria-label={`Toggle memory ${memory.is_active ? 'off' : 'on'}`}
                      onClick={() => handleToggleMemory(memory.id, memory.is_active)}
                      className={`w-9 h-5 rounded-full transition-colors relative flex-shrink-0 ${
                        memory.is_active ? "bg-rausch" : "bg-canvas-strong"
                      }`}
                    >
                      <span
                        className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-canvas shadow transition-transform"
                        style={{ transform: `translateX(${memory.is_active ? "16px" : "0"})` }}
                      />
                    </button>
                    <button
                      onClick={() => handleDeleteMemory(memory.id)}
                      className="w-7 h-7 rounded flex items-center justify-center text-ink-muted hover:bg-rausch-light hover:text-error opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </section>

        {/* Account Section */}
        <section className="animate-fade-in-up" style={{ animationDelay: "300ms" } as React.CSSProperties}>
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-ink-muted" />
            <h2 className="text-title-md text-ink">Account</h2>
          </div>
          <Card className="p-6 space-y-4">
            <button
              onClick={handleExportData}
              className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-canvas-soft transition-colors text-left"
            >
              <Download className="w-5 h-5 text-ink-muted" />
              <div>
                <p className="text-body-sm text-ink font-medium">Export Data</p>
                <p className="text-caption-sm text-ink-muted-soft">Download all your data as JSON</p>
              </div>
            </button>

            <button
              onClick={() => setShowSignOutModal(true)}
              className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-canvas-soft transition-colors text-left"
            >
              <LogOut className="w-5 h-5 text-ink-muted" />
              <div>
                <p className="text-body-sm text-ink font-medium">Sign Out</p>
                <p className="text-caption-sm text-ink-muted-soft">Sign out from all devices</p>
              </div>
            </button>

            <div className="pt-2 border-t border-border">
              <button
                onClick={() => setShowDeleteModal(true)}
                className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-rausch-light transition-colors text-left"
              >
                <Trash2 className="w-5 h-5 text-error" />
                <div>
                  <p className="text-body-sm text-error font-medium">Delete Account</p>
                  <p className="text-caption-sm text-ink-muted-soft">Permanently delete your account and data</p>
                </div>
              </button>
            </div>
          </Card>
        </section>
      </div>

      {/* Add Memory Modal */}
      <Modal open={showAddMemory} onClose={() => setShowAddMemory(false)} title="Add Memory">
        <div className="space-y-4">
          <div>
            <label className="block text-caption text-ink-muted mb-1.5">Type</label>
            <div className="flex gap-2">
              {(["FACT", "PREFERENCE", "GOAL"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => setNewMemoryType(type)}
                  className={`px-4 py-2 rounded-full text-body-sm font-medium transition-all ${
                    newMemoryType === type
                      ? "bg-rausch text-white"
                      : "bg-canvas-soft text-ink hover:bg-canvas-strong"
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-caption text-ink-muted mb-1.5">Content</label>
            <textarea
              value={newMemoryContent}
              onChange={(e) => setNewMemoryContent(e.target.value)}
              placeholder="What should the AI remember?"
              rows={3}
              className="input-airbnb resize-none"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setShowAddMemory(false)}>Cancel</Button>
            <Button onClick={handleAddMemory} disabled={!newMemoryContent.trim()}>Add</Button>
          </div>
        </div>
      </Modal>

      {/* Sign Out Modal */}
      <Modal open={showSignOutModal} onClose={() => setShowSignOutModal(false)} title="Sign Out">
        <p className="text-body-md text-ink-muted mb-6">
          Are you sure you want to sign out?
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowSignOutModal(false)}>Cancel</Button>
          <Button variant="danger" onClick={handleSignOut}>Sign Out</Button>
        </div>
      </Modal>

      {/* Delete Account Modal */}
      <Modal open={showDeleteModal} onClose={() => setShowDeleteModal(false)} title="Delete Account">
        <p className="text-body-md text-ink-muted mb-6">
          This action cannot be undone. All your data, conversations, flashcards, and quizzes will be permanently deleted.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setShowDeleteModal(false)}>Cancel</Button>
          <Button variant="danger" onClick={() => { setShowDeleteModal(false); toast("Account deletion requested", "info"); }}>Delete Account</Button>
        </div>
      </Modal>
    </ProtectedLayout>
  );
}
