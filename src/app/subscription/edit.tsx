import { Feather } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Chip, FormField, Input, PrimaryButton, SecondaryButton, SegmentedControl } from '@/components/ui';
import { CATEGORY_LABEL, type BillingCycle, type Category } from '@/domain/types';
import { useAppStore } from '@/store/AppStore';
import { colors, font, radius, space } from '@/theme/tokens';

const CATEGORIES = Object.keys(CATEGORY_LABEL) as Category[];

export default function EditSubscription() {
	const { id } = useLocalSearchParams<{ id: string }>();
	const { subscriptions, updateSubscription } = useAppStore();

	// 수정할 기존 구독 찾기
	const targetSub = subscriptions.find((s) => s.id === id);

	// 기존 값으로 상태 초기화
	const [name, setName] = useState(targetSub?.name ?? '');
	const [amount, setAmount] = useState(targetSub ? String(targetSub.amount) : '');
	const [cycle, setCycle] = useState<BillingCycle>(targetSub?.cycle ?? 'monthly');
	const [billingDay, setBillingDay] = useState(targetSub?.billingDay ?? 15);
	const [billingMonth, setBillingMonth] = useState(targetSub?.billingMonth ?? 1);
	const [memo, setMemo] = useState(targetSub?.memo ?? '');
	const [category, setCategory] = useState<Category>(targetSub?.category ?? 'ott');
	const [showSavings, setShowSavings] = useState(targetSub?.showSavings ?? true);
	const [picker, setPicker] = useState<null | 'day' | 'month'>(null);

	const amountNum = Number(amount.replace(/[^0-9]/g, ''));
	const valid = name.trim().length > 0 && amountNum > 0;

	const saveEdit = async () => {
		if (!valid || !targetSub) return;

		await updateSubscription(targetSub.id, {
			name: name.trim(),
			amount: amountNum,
			cycle,
			billingDay,
			billingMonth: cycle === 'yearly' ? billingMonth : undefined,
			category,
			memo,
			showSavings,
		});
		router.back();
	};

	return (
		<SafeAreaView style={styles.container}>
			{/* 상단 헤더: 제목 '구독 수정', 우측 '완료' 버튼 */}
			<View style={styles.header}>
				<Pressable onPress={() => router.back()} hitSlop={10}>
					<Feather name="arrow-left" size={20} color={colors.text} />
				</Pressable>
				<Text style={font.heading}>구독 수정</Text>
				<Pressable onPress={saveEdit} disabled={!valid} hitSlop={10}>
					<Text style={[styles.done, !valid && { opacity: 0.4 }]}>완료</Text>
				</Pressable>
			</View>

			<ScrollView contentContainerStyle={{ padding: space.xl }} keyboardShouldPersistTaps="handled">
				<FormField label="서비스 이름">
					<Input value={name} onChangeText={setName} placeholder="서비스 이름 입력" />
				</FormField>

				<FormField label="결제 금액">
					<Input
						value={amount ? Number(amountNum).toLocaleString('ko-KR') : ''}
						onChangeText={setAmount}
						placeholder="17,000원"
						keyboardType="number-pad"
					/>
				</FormField>

				<FormField label="결제 주기">
					<SegmentedControl
						value={cycle}
						onChange={setCycle}
						options={[
							{ value: 'monthly', label: '매월' },
							{ value: 'yearly', label: '매년' },
						]}
					/>
				</FormField>

				<FormField label="결제일">
					<View style={{ flexDirection: 'row', gap: space.sm }}>
						{cycle === 'yearly' && (
							<Pressable style={[styles.select, { flex: 1 }]} onPress={() => setPicker('month')}>
								<Text style={font.body}>{billingMonth}월</Text>
								<Feather name="chevron-down" size={18} color={colors.textSub} />
							</Pressable>
						)}
						<Pressable style={[styles.select, { flex: 1 }]} onPress={() => setPicker('day')}>
							<Text style={font.body}>{billingDay}일</Text>
							<Feather name="chevron-down" size={18} color={colors.textSub} />
						</Pressable>
					</View>
				</FormField>

				<FormField label="메모">
					<Input value={memo} onChangeText={setMemo} placeholder="메모 입력" />
				</FormField>

				<FormField label="카테고리">
					<View style={styles.chipBox}>
						{CATEGORIES.map((c) => (
							<Chip key={c} label={CATEGORY_LABEL[c]} selected={c === category} onPress={() => setCategory(c)} />
						))}
					</View>
				</FormField>

				<View style={styles.savings}>
					<Feather name="star" size={18} color={colors.primary} />
					<View style={{ flex: 1, marginHorizontal: space.md }}>
						<Text style={[font.label, { fontSize: 12 }]}>해지하면 매년 얼마를 절약할 수 있어요!</Text>
						<Text style={[font.caption, { fontSize: 11 }]}>절약 예상 금액을 분석에 표시해요.</Text>
					</View>
					<Switch
						value={showSavings}
						onValueChange={setShowSavings}
						trackColor={{ true: colors.primary, false: colors.border }}
						thumbColor="#fff"
						{...({ activeThumbColor: '#fff' } as object)}
					/>
				</View>

				{/* 하단 버튼: '저장' 대신 '수정'으로 변경 */}
				<PrimaryButton title="수정" onPress={saveEdit} disabled={!valid} style={{ marginTop: space.xxl }} />
				<SecondaryButton title="취소" onPress={() => router.back()} />
			</ScrollView>

			<NumberPicker
				visible={picker !== null}
				values={picker === 'month' ? range(1, 12) : range(1, 31)}
				suffix={picker === 'month' ? '월' : '일'}
				selected={picker === 'month' ? billingMonth : billingDay}
				onSelect={(v) => {
					if (picker === 'month') setBillingMonth(v);
					else setBillingDay(v);
					setPicker(null);
				}}
				onClose={() => setPicker(null)}
			/>
		</SafeAreaView>
	);
}

const range = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i);

function NumberPicker({
	visible,
	values,
	suffix,
	selected,
	onSelect,
	onClose,
}: {
	visible: boolean;
	values: number[];
	suffix: string;
	selected: number;
	onSelect: (v: number) => void;
	onClose: () => void;
}) {
	return (
		<Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
			<Pressable style={styles.backdrop} onPress={onClose}>
				<Pressable style={styles.sheet}>
					<View style={styles.grid}>
						{values.map((v) => (
							<Pressable
								key={v}
								onPress={() => onSelect(v)}
								style={[styles.cell, v === selected && { backgroundColor: colors.primary }]}
							>
								<Text style={{ color: v === selected ? '#fff' : colors.text, fontSize: 13 }}>
									{v}
									{suffix}
								</Text>
							</Pressable>
						))}
					</View>
				</Pressable>
			</Pressable>
		</Modal>
	);
}

const styles = StyleSheet.create({
	container: { flex: 1, backgroundColor: colors.bg },
	header: {
		flexDirection: 'row',
		justifyContent: 'space-between',
		alignItems: 'center',
		paddingHorizontal: space.xl,
		paddingVertical: space.md,
	},
	done: { color: colors.primary, fontWeight: '700', fontSize: 14 },
	select: {
		flexDirection: 'row',
		justifyContent: 'space-between',
		alignItems: 'center',
		backgroundColor: colors.surface,
		borderWidth: 1,
		borderColor: colors.border,
		borderRadius: radius.md,
		paddingHorizontal: 14,
		paddingVertical: 14,
	},
	chipBox: {
		flexDirection: 'row',
		flexWrap: 'wrap',
		gap: space.sm,
		backgroundColor: colors.surface,
		borderRadius: radius.md,
		padding: space.md,
	},
	savings: {
		flexDirection: 'row',
		alignItems: 'center',
		backgroundColor: colors.primarySoft,
		borderRadius: radius.md,
		padding: space.lg,
	},
	backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)', justifyContent: 'flex-end' },
	sheet: { backgroundColor: '#fff', borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: space.xl, paddingBottom: 40 },
	grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
	cell: { width: '12.5%', minWidth: 40, paddingVertical: 10, alignItems: 'center', borderRadius: radius.sm, backgroundColor: colors.surface },
});
