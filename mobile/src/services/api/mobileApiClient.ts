import type { MobileConfig } from "@/config/mobileConfig";
import { getAccessToken } from "@/services/auth/amplifyAuth";

export type MobileApiRequest = {
  path: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
};

export type MobileApiErrorBody = {
  detail?: string;
  code?: string;
  support_code?: string;
};

export class MobileApiError extends Error {
  status: number;
  body: MobileApiErrorBody;

  constructor(status: number, body: MobileApiErrorBody) {
    super(body.detail || body.code || `STOA API request failed with status ${status}`);
    this.name = "MobileApiError";
    this.status = status;
    this.body = body;
  }
}

export const createMobileApiClient = (config: MobileConfig) => {
  return async function request<T>(requestOptions: MobileApiRequest): Promise<T> {
    const accessToken = await getAccessToken();
    const response = await fetch(`${config.apiBaseUrl}${requestOptions.path}`, {
      method: requestOptions.method ?? "GET",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...requestOptions.headers
      },
      body: requestOptions.body ? JSON.stringify(requestOptions.body) : undefined
    });

    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as MobileApiErrorBody;
      throw new MobileApiError(response.status, body);
    }

    return (await response.json()) as T;
  };
};
