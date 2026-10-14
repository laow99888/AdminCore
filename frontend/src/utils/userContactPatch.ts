/** Empty edit inputs preserve masked contact fields; clearing a phone is explicit. */
export function userContactPatch(email: string, phone: string, clearPhone: boolean): { email?: string; phone?: string } {
  const nextEmail = email.trim(), nextPhone = phone.trim()
  if (nextEmail.includes('*') || (!clearPhone && nextPhone.includes('*'))) throw new Error('masked-contact')
  return { ...(nextEmail ? { email: nextEmail } : {}), ...(clearPhone ? { phone: '' } : nextPhone ? { phone: nextPhone } : {}) }
}
