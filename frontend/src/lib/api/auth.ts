/**
 * /auth/* 接口封装。后端契约:
 *   POST /auth/register             JSON  body
 *   POST /auth/register/merchant    JSON  body
 *   POST /auth/login                FormData (OAuth2PasswordRequestForm)
 *   POST /auth/sms/send             JSON  { phone }
 *   POST /auth/sms/login            JSON  { phone, code }
 *   GET  /auth/me                   Bearer token
 */

import { apiGet, apiPost } from './client';
import type {
  CurrentUser,
  MerchantRegisterRequest,
  RegisterRequest,
  SmsLoginRequest,
  TokenResponse,
} from '../types';

export const authApi = {
  register(body: RegisterRequest) {
    return apiPost<CurrentUser>('/auth/register', { json: body, skipAuth: true });
  },

  registerMerchant(body: MerchantRegisterRequest) {
    return apiPost<CurrentUser>('/auth/register/merchant', { json: body, skipAuth: true });
  },

  /** 账密登录:OAuth2PasswordRequestForm 要 form 不要 JSON */
  login(username: string, password: string) {
    const form = new URLSearchParams();
    form.set('username', username);
    form.set('password', password);
    return apiPost<TokenResponse>('/auth/login', { urlEncoded: form, skipAuth: true });
  },

  sendSms(phone: string) {
    return apiPost<{ sent: boolean; ttl_seconds: number }>('/auth/sms/send', {
      json: { phone },
      skipAuth: true,
    });
  },

  /** 手机号 + 验证码登录,首次自动注册 */
  smsLogin(body: SmsLoginRequest) {
    return apiPost<TokenResponse>('/auth/sms/login', { json: body, skipAuth: true });
  },

  me() {
    return apiGet<CurrentUser>('/auth/me');
  },
};
