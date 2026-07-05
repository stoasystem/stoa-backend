export type StudentScreenContract = {
  route: string;
  titleKey: string;
  endpointContracts: string[];
  states: Array<"loading" | "ready" | "empty" | "blocked" | "stale" | "error">;
  offlineReadThrough: boolean;
  onlineOnlyMutations: string[];
};

export const STUDENT_SCREEN_CONTRACTS: StudentScreenContract[] = [
  {
    route: "/student",
    titleKey: "studentDashboard",
    endpointContracts: ["/students/me/profile", "/practice/overview", "/notifications"],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  },
  {
    route: "/student/practice",
    titleKey: "practice",
    endpointContracts: [
      "/practice/overview",
      "/practice/curriculum/catalog",
      "/practice/curriculum/progress",
      "/practice/curriculum/lessons/{lessonId}",
      "/practice/teacher-help"
    ],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: ["/practice/teacher-help", "/practice/challenges/{challengeId}/answer"]
  },
  {
    route: "/student/questions",
    titleKey: "askQuestion",
    endpointContracts: ["/questions", "/questions/{questionId}/request-teacher"],
    states: ["loading", "ready", "empty", "blocked", "error"],
    offlineReadThrough: false,
    onlineOnlyMutations: ["/questions", "/questions/{questionId}/request-teacher"]
  },
  {
    route: "/student/history",
    titleKey: "learningHistory",
    endpointContracts: ["/students/{studentId}/questions"],
    states: ["loading", "ready", "empty", "blocked", "stale", "error"],
    offlineReadThrough: true,
    onlineOnlyMutations: []
  }
];
