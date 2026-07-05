import type { createMobileApiClient } from "@/services/api/mobileApiClient";

type MobileApiClient = ReturnType<typeof createMobileApiClient>;

export type StudentProfile = {
  id: string;
  email: string;
  name?: string;
  grade?: string;
  language?: string;
  subscriptionTier?: string;
};

export type StudentDashboardSummary = {
  profile: StudentProfile;
  practiceOverview: unknown;
  notifications: unknown;
};

export type SubmitQuestionInput = {
  content: string;
  subject: string;
  idempotencyKey: string;
  imageS3Key?: string;
  correctedText?: string;
};

export type PracticeTeacherHelpInput = {
  lessonId?: string;
  challengeId?: string;
  message: string;
};

export const createStudentApi = (api: MobileApiClient) => ({
  getProfile: () => api<StudentProfile>({ path: "/students/me/profile" }),

  getPracticeOverview: () => api<unknown>({ path: "/practice/overview" }),

  getCurriculumCatalog: () => api<unknown>({ path: "/practice/curriculum/catalog" }),

  getCurriculumProgress: () => api<unknown>({ path: "/practice/curriculum/progress" }),

  getLesson: (lessonId: string) =>
    api<unknown>({ path: `/practice/curriculum/lessons/${encodeURIComponent(lessonId)}` }),

  submitQuestion: (input: SubmitQuestionInput) =>
    api<unknown>({
      path: "/questions",
      method: "POST",
      body: {
        content: input.content,
        subject: input.subject,
        idempotency_key: input.idempotencyKey,
        image_s3_key: input.imageS3Key,
        corrected_text: input.correctedText
      }
    }),

  requestTeacherForQuestion: (questionId: string) =>
    api<unknown>({
      path: `/questions/${encodeURIComponent(questionId)}/request-teacher`,
      method: "POST"
    }),

  requestPracticeTeacherHelp: (input: PracticeTeacherHelpInput) =>
    api<unknown>({
      path: "/practice/teacher-help",
      method: "POST",
      body: input
    }),

  getStudentQuestions: (studentId: string) =>
    api<unknown>({ path: `/students/${encodeURIComponent(studentId)}/questions` }),

  getNotifications: () => api<unknown>({ path: "/notifications" }),

  getDashboardSummary: async (): Promise<StudentDashboardSummary> => {
    const profile = await api<StudentProfile>({ path: "/students/me/profile" });
    const [practiceOverview, notifications] = await Promise.all([
      api<unknown>({ path: "/practice/overview" }),
      api<unknown>({ path: "/notifications" })
    ]);

    return {
      profile,
      practiceOverview,
      notifications
    };
  }
});
