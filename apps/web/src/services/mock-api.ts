import {
  mockArtifacts,
  mockMessages,
  mockModels,
  mockSessions,
  mockSkills,
  mockUser,
} from "./mock-data";

export const mockApi = {
  getCurrentUser: async () => mockUser,
  getSessions: async () => mockSessions,
  getMessages: async (sessionId: string) =>
    mockMessages.filter((message) => message.sessionId === sessionId),
  getSkills: async () => mockSkills,
  getArtifacts: async (sessionId: string) =>
    mockArtifacts.filter((artifact) => artifact.sessionId === sessionId),
  getModels: async () => mockModels,
};

