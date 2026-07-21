import { apiClient } from "../api-client";
import type {
  DataContextSettings,
  InterfaceSettings,
  ModelConfig,
  Skill,
  SkillKey,
  User,
} from "@/types";
import type {
  ModelCreateInput,
  PasswordUpdateInput,
  PasswordUpdateResult,
  ProfileUpdateInput,
  SettingsApiAdapter,
} from "./types";

export const fastApiSettingsAdapter: SettingsApiAdapter = {
  addModel(input: ModelCreateInput) {
    return apiClient<ModelConfig>("/api/settings/models", {
      body: JSON.stringify(input),
      method: "POST",
    });
  },
  deleteModel(modelId: string) {
    return apiClient<void>(`/api/settings/models/${modelId}`, {
      method: "DELETE",
    });
  },
  getDataContextSettings() {
    return apiClient<DataContextSettings>("/api/settings/data-context");
  },
  getInterfaceSettings() {
    return apiClient<InterfaceSettings>("/api/settings/interface");
  },
  setDefaultModel(modelId: string) {
    return apiClient<ModelConfig[]>("/api/settings/models/default", {
      body: JSON.stringify({ model_id: modelId }),
      method: "POST",
    });
  },
  setDefaultSkill(skillKey: SkillKey) {
    return apiClient<Skill[]>("/api/settings/skills/default", {
      body: JSON.stringify({ skill_key: skillKey }),
      method: "POST",
    });
  },
  testModelConnection(modelId: string) {
    return apiClient<ModelConfig>(`/api/settings/models/${modelId}/test`, {
      method: "POST",
    });
  },
  toggleSkillEnabled(skillKey: SkillKey) {
    return apiClient<Skill[]>(`/api/settings/skills/${skillKey}/toggle`, {
      method: "POST",
    });
  },
  updateDataContextSettings(input: DataContextSettings) {
    return apiClient<DataContextSettings>("/api/settings/data-context", {
      body: JSON.stringify(input),
      method: "PUT",
    });
  },
  updateInterfaceSettings(input: InterfaceSettings) {
    return apiClient<InterfaceSettings>("/api/settings/interface", {
      body: JSON.stringify(input),
      method: "PUT",
    });
  },
  updateModel(modelId: string, input: Partial<ModelConfig>) {
    return apiClient<ModelConfig>(`/api/settings/models/${modelId}`, {
      body: JSON.stringify(input),
      method: "PUT",
    });
  },
  updateProfile(input: ProfileUpdateInput) {
    return apiClient<User>("/api/settings/profile", {
      body: JSON.stringify(input),
      method: "PUT",
    });
  },
  async updatePassword(input: PasswordUpdateInput) {
    const result = await apiClient<PasswordUpdateResult>("/api/settings/profile/password", {
      body: JSON.stringify(input),
      method: "PUT",
    });

    if (result?.accessToken && typeof window !== "undefined") {
      window.localStorage.setItem("webagent_access_token", result.accessToken);
    }

    return result;
  },
  updateSkillVersion(skillKey: SkillKey, direction: "rollback" | "update") {
    return apiClient<Skill[]>(`/api/settings/skills/${skillKey}/version`, {
      body: JSON.stringify({ direction }),
      method: "POST",
    });
  },
};
