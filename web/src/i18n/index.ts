/** `fr` is the product language; `en` is scaffolded for foreign visiting crews (docs/09). */
import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import fr from './fr.json'
import en from './en.json'

export const defaultLanguage = 'fr'

void i18next.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: defaultLanguage,
  fallbackLng: defaultLanguage,
  interpolation: { escapeValue: false },
})

export default i18next
