import type { DataContextSettings, ModelConfig, Skill, SkillKey, User } from "@/types";
import { mockModels, mockSkills, mockUser } from "../mock-data";
import type {
  ModelCreateInput,
  ProfileUpdateInput,
  SettingsApiAdapter,
} from "./types";

let user: User = { ...mockUser };
let models: ModelConfig[] = [...mockModels];
let skills: Skill[] = [...mockSkills];
let dataContextSettings: DataContextSettings = {
  autoSummarizeContext: true,
  contextRetentionDays: 30,
  maxContextMessages: 40,
  saveConversationHistory: true,
  saveUploadedFiles: true,
};

function createId(prefix: string) {
  return `${prefix}_${Date.now()}`;
}

function wait(ms = 350) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export const mockSettingsAdapter: SettingsApiAdapter = {
  async addModel(input: ModelCreateInput) {
    await wait();
    const model: ModelConfig = {
      ...input,
      id: createId("model"),
      isAvailable: true,
      isDefault: false,
      maskedApiKey: input.maskedApiKey || "sk-****",
    };

    models = [...models, model];
    return model;
  },
  async deleteModel(modelId: string) {
    await wait();
    const model = models.find((item) => item.id === modelId);

    if (model?.isDefault) {
      return;
    }

    models = models.filter((item) => item.id !== modelId);
  },
  async getDataContextSettings() {
    await wait(150);
    return dataContextSettings;
  },
  async setDefaultModel(modelId: string) {
    await wait();
    models = models.map((model) => ({
      ...model,
      isDefault: model.id === modelId,
    }));
    return models;
  },
  async setDefaultSkill(skillKey: SkillKey) {
    await wait();
    skills = skills.map((skill) => ({
      ...skill,
      isDefault: skill.key === skillKey,
    }));
    return skills;
  },
  async testModelConnection(modelId: string) {
    await wait(700);
    const model = models.find((item) => item.id === modelId);

    if (!model) {
      throw new Error("Model not found");
    }

    const updatedModel = { ...model, isAvailable: true };
    models = models.map((item) => (item.id === modelId ? updatedModel : item));
    return updatedModel;
  },
  async toggleSkillEnabled(skillKey: SkillKey) {
    await wait();
    skills = skills.map((skill) =>
      skill.key === skillKey
        ? {
            ...skill,
            enabled: !skill.enabled,
            isDefault: skill.enabled ? false : skill.isDefault,
          }
        : skill,
    );
    return skills;
  },
  async updateDataContextSettings(input: DataContextSettings) {
    await wait();
    dataContextSettings = input;
    return dataContextSettings;
  },
  async updateModel(modelId: string, input: Partial<ModelConfig>) {
    await wait();
    const model = models.find((item) => item.id === modelId);

    if (!model) {
      throw new Error("Model not found");
    }

    const updatedModel = { ...model, ...input };
    models = models.map((item) => (item.id === modelId ? updatedModel : item));
    return updatedModel;
  },
  async updateProfile(input: ProfileUpdateInput) {
    await wait();
    user = { ...user, ...input };
    return user;
  },
  async updatePassword() {
    await wait();
    return undefined;
  },
  async updateSkillVersion(skillKey: SkillKey, direction: "rollback" | "update") {
    await wait(600);
    skills = skills.map((skill) => {
      if (skill.key !== skillKey) {
        return skill;
      }

      const [major = 1, minor = 0, patch = 0] = skill.version
        .split(".")
        .map((value) => Number(value));
      const nextPatch =
        direction === "update" ? patch + 1 : Math.max(0, patch - 1);

      return {
        ...skill,
        lastUpdatedAt: new Date().toISOString(),
        version: `${major}.${minor}.${nextPatch}`,
      };
    });
    return skills;
  },
};
