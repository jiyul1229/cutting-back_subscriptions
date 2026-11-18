// 구독 추가·수정 화면: 다른 사람과 같이 결제하는 구독의 인원을 정하고 내 몫을 미리 보여준다.
import { Feather } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { formatWon } from '@/domain/engine';
import { colors, font, radius, space } from '@/theme/tokens';

export const MIN_SPLIT = 2;
export const MAX_SPLIT = 10;

/**
 * value: 나눠 내는 인원(나 포함). 1이면 혼자 쓰는 구독이라 '같이 쓰기' 버튼만 보인다.
 * amount: 1회 결제 총액. 내 몫 미리보기에 쓴다.
 */
export function SplitField({
  value,
  onChange,
  amount,
}: {
  value: number;
  onChange: (n: number) => void;
  amount: number;
}) {
  if (value <= 1) {
    return (
      <Pressable
        onPress={() => onChange(MIN_SPLIT)}
        style={({ pressed }) => [styles.addBtn, pressed && { opacity: 0.7 }]}
      >
        <Feather name="users" size={16} color={colors.primary} />
        <Text style={styles.addBtnText}>다른 사람과 같이 쓰기</Text>
      </Pressable>
    );
  }

  const share = Math.round(amount / value);
  return (
    <View style={styles.box}>
      <View style={styles.row}>
        <Feather name="users" size={18} color={colors.primary} />
        <Text style={[font.label, { flex: 1, marginLeft: space.md }]}>같이 쓰는 인원 (나 포함)</Text>
        <StepButton icon="minus" disabled={value <= MIN_SPLIT} onPress={() => onChange(value - 1)} />
        <Text style={styles.count}>{value}명</Text>
        <StepButton icon="plus" disabled={value >= MAX_SPLIT} onPress={() => onChange(value + 1)} />
      </View>
      <View style={[styles.row, { marginTop: space.md }]}>
        <Text style={[font.caption, { flex: 1 }]}>
          {amount > 0 ? `${formatWon(amount)} ÷ ${value}명` : '결제 금액을 입력하면 내 몫을 계산해요'}
        </Text>
        {amount > 0 && <Text style={styles.share}>내 몫 {formatWon(share)}</Text>}
      </View>
      <Pressable onPress={() => onChange(1)} hitSlop={8} style={{ alignSelf: 'flex-start', marginTop: space.md }}>
        <Text style={styles.remove}>혼자 쓰기로 바꾸기</Text>
      </Pressable>
    </View>
  );
}

function StepButton({
  icon,
  disabled,
  onPress,
}: {
  icon: 'minus' | 'plus';
  disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      hitSlop={6}
      style={[styles.step, disabled && { opacity: 0.35 }]}
    >
      <Feather name={icon} size={14} color={colors.text} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: 14,
  },
  addBtnText: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  box: { backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: space.lg },
  row: { flexDirection: 'row', alignItems: 'center' },
  step: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  count: { width: 40, textAlign: 'center', fontWeight: '700', color: colors.text },
  share: { color: colors.primary, fontWeight: '800', fontSize: 15 },
  remove: { color: colors.textSub, fontSize: 12, textDecorationLine: 'underline' },
});
