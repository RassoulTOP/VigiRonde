import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button, colors, Muted } from '@/components/ui';
import { ApiError } from '@/lib/api';
import { useSession } from '@/lib/session';

export default function Login() {
  const { login, apiUrl } = useSession();
  const [email, setEmail] = useState('agent@demo.vigironde.fr');
  const [password, setPassword] = useState('');
  const [server, setServer] = useState(apiUrl);
  const [showServer, setShowServer] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      await login(email, password, server);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.status === 401
            ? 'Email ou mot de passe incorrect'
            : e.message
          : `Serveur injoignable (${server}). Le téléphone et le Mac sont-ils sur le même Wi-Fi ?`,
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.wrap}>
        <View style={{ alignItems: 'center', gap: 6, marginBottom: 28 }}>
          <View style={s.logo}>
            <Text style={{ fontSize: 34 }}>🛡️</Text>
          </View>
          <Text style={s.brand}>VigiRonde</Text>
          <Muted>Rondes, vacations et incidents — agents de sécurité</Muted>
        </View>

        <TextInput
          style={s.input}
          value={email}
          onChangeText={setEmail}
          placeholder="Email"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
        />
        <TextInput
          style={s.input}
          value={password}
          onChangeText={setPassword}
          placeholder="Mot de passe"
          placeholderTextColor={colors.muted}
          secureTextEntry
          autoComplete="password"
          onSubmitEditing={submit}
        />
        {showServer && (
          <TextInput
            style={s.input}
            value={server}
            onChangeText={setServer}
            placeholder="http://192.168.x.x:8000"
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            keyboardType="url"
          />
        )}
        {error && <Text style={s.error}>{error}</Text>}
        <Button title="Se connecter" onPress={submit} loading={loading} disabled={!email || !password} big />
        <Pressable onPress={() => setShowServer((v) => !v)} style={{ marginTop: 18, alignSelf: 'center' }}>
          <Muted>Serveur : {server} {showServer ? '▲' : '▼'}</Muted>
        </Pressable>
        <Muted style={{ textAlign: 'center', marginTop: 24, fontSize: 12 }}>
          Démo : agent@demo.vigironde.fr · VigiRonde2026! — données fictives
        </Muted>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, justifyContent: 'center', padding: 24, gap: 12 },
  logo: {
    width: 72,
    height: 72,
    borderRadius: 20,
    backgroundColor: colors.primaryDark,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brand: { color: colors.text, fontSize: 30, fontWeight: '900', letterSpacing: 0.5 },
  input: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
  },
  error: { color: colors.danger, fontSize: 14 },
});
