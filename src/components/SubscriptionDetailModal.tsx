import { Feather } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { formatWon, nextBillingDate } from '@/domain/engine';
import { type Category, type Subscription } from '@/domain/types';
import { colors, font, radius, space } from '@/theme/tokens';

const CATEGORY_COLORS: Record<Category | 'learning' | 'study', { bg: string; text: string }> = {
  ott: { bg: '#FFE5E6', text: '#E50914' },
  book: { bg: '#FFF4E5', text: '#FF9500' },
  shopping: { bg: '#E5F0FF', text: '#007AFF' },
  learning: { bg: '#E8F8F0', text: '#00C73C' },
  study: { bg: '#E8F8F0', text: '#00C73C' },
  lifestyle: { bg: '#F2E8FF', text: '#AF52DE' },
  software: { bg: '#E0F7FA', text: '#00838F' },
  etc: { bg:'#ffeefc', text: '#ff77e1' },
};

type Props = {
  visible: boolean;
  subscription: Subscription | null;
  onClose: () => void;
  onDelete: (id: string) => void;
};

export function SubscriptionDetailModal({ visible, subscription, onClose, onDelete }: Props) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  
  // 시안에 맞춰 스위치 상태 관리 (필요 시 추후 스토어 업데이트와 연동 가능)
  const [showSavings, setShowSavings] = useState(subscription?.showSavings ?? true);
  const [billingAlert, setBillingAlert] = useState(true);

  if (!subscription) return null;

  const catStyle = CATEGORY_COLORS[subscription.category] || { bg: colors.primarySoft, text: colors.primary };
  const nextDate = nextBillingDate(subscription);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      {/* 어두운 배경 누르면 닫히기 */}
      <Pressable style={styles.backdrop} onPress={onClose}>
        {/* 모달 내부 클릭 시 닫힘 방지 */}
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handleBar} />

          {/* 서비스 대표 아이콘 */}
          <View style={[styles.iconBox, { backgroundColor: catStyle.bg }]}>
            <Text style={[styles.iconText, { color: catStyle.text }]}>
              {subscription.name[0]?.toUpperCase()}
            </Text>
          </View>

          <Text style={styles.subName}>{subscription.name}</Text>
          <Text style={styles.subMemo}>{subscription.memo || '나만의 메모 추가'}</Text>
          <Text style={styles.subPrice}>{formatWon(subscription.amount)} / 월</Text>

          <View style={styles.infoBox}>
            <View style={styles.infoRow}>
              <Text style={font.caption}>등록일</Text>
              <Text style={font.label}>2023.03.15</Text>
            </View>
            <View style={styles.infoRow}>
              <Text style={font.caption}>다음 결제일</Text>
              <Text style={font.label}>
                {nextDate.getFullYear()}.{String(nextDate.getMonth() + 1).padStart(2, '0')}.{String(nextDate.getDate()).padStart(2, '0')}
              </Text>
            </View>

            {/* 분석 표시 및 결제 알림 스위치 영역 */}
            <View style={styles.switchRowContainer}>
              <View style={styles.switchItem}>
                <Text style={font.caption}>분석 표시</Text>
                <Switch
                  value={showSavings}
                  onValueChange={setShowSavings}
                  trackColor={{ true: colors.primary, false: colors.border }}
                  thumbColor="#fff"
                  {...({ activeThumbColor: '#fff' } as object)}
                />
              </View>
              <View style={styles.switchDivider} />
              <View style={styles.switchItem}>
                <Text style={font.caption}>결제 알림</Text>
                <Switch
                  value={billingAlert}
                  onValueChange={setBillingAlert}
                  trackColor={{ true: colors.primary, false: colors.border }}
                  thumbColor="#fff"
                  {...({ activeThumbColor: '#fff' } as object)}
                />
              </View>
            </View>
          </View>

          {/* 하단 버튼 영역 */}
          <View style={styles.buttonRow}>
            <Pressable
              style={styles.editButton}
              onPress={() => {
                onClose();
                router.push({
                  pathname: '/subscription/edit',
                  params: { id: subscription.id },
                });
              }}
            >
              <Text style={styles.editText}>수정</Text>
            </Pressable>
            <Pressable style={styles.deleteButton} onPress={() => setShowDeleteConfirm(true)}>
              <Text style={styles.deleteText}>삭제</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>

      {/* 삭제 확인 경고 팝업 */}
      <Modal visible={showDeleteConfirm} transparent animationType="fade">
        <View style={styles.confirmBackdrop}>
          <View style={styles.confirmBox}>
            <View style={styles.warningIconBox}>
              <Feather name="alert-triangle" size={24} color="#FF3B30" />
            </View>
            <Text style={font.heading}>구독 삭제</Text>
            <Text style={styles.confirmDesc}>정말 삭제하시겠습니까?{'\n'}이 작업은 되돌릴 수 없습니다.</Text>
            
            <View style={styles.confirmBtnRow}>
              <Pressable style={styles.cancelBtn} onPress={() => setShowDeleteConfirm(false)}>
                <Text style={styles.cancelBtnText}>취소</Text>
              </Pressable>
              <Pressable
                style={styles.okBtn}
                onPress={() => {
                  setShowDeleteConfirm(false);
                  onDelete(subscription.id);
                  onClose();
                }}
              >
                <Text style={styles.okBtnText}>삭제</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: '#fff', borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: space.xl, alignItems: 'center' },
  handleBar: { width: 40, height: 4, backgroundColor: colors.border, borderRadius: radius.pill, marginBottom: space.lg },
  iconBox: { width: 56, height: 56, borderRadius: radius.lg, alignItems: 'center', justifyContent: 'center', marginBottom: space.md },
  iconText: { fontSize: 24, fontWeight: '800' },
  subName: { fontSize: 18, fontWeight: '800', color: colors.text, marginBottom: 2 },
  subMemo: { fontSize: 13, color: colors.textSub, marginBottom: space.md },
  subPrice: { fontSize: 20, fontWeight: '800', color: colors.primary, marginBottom: space.xl },
  infoBox: { width: '100%', backgroundColor: colors.surface, borderRadius: radius.md, padding: space.lg, gap: space.md, marginBottom: space.xl },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  
  // 스위치 영역 스타일
  switchRowContainer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: space.xs },
  switchItem: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flex: 1, justifyContent: 'space-between' },
  switchDivider: { width: 1, height: 20, backgroundColor: colors.border, marginHorizontal: space.md },

  buttonRow: { flexDirection: 'row', gap: space.md, width: '100%', marginBottom: space.md },
  editButton: { flex: 1, backgroundColor: colors.primarySoft, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  editText: { color: colors.primary, fontWeight: '700', fontSize: 15 },
  deleteButton: { flex: 1, backgroundColor: colors.primary, paddingVertical: 14, borderRadius: radius.md, alignItems: 'center' },
  deleteText: { color: '#fff', fontWeight: '700', fontSize: 15 },

  confirmBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', padding: space.xl },
  confirmBox: { width: '100%', maxWidth: 320, backgroundColor: '#fff', borderRadius: radius.xl, padding: space.xl, alignItems: 'center' },
  warningIconBox: { width: 48, height: 48, borderRadius: 24, backgroundColor: '#FFF5F5', alignItems: 'center', justifyContent: 'center', marginBottom: space.md },
  confirmDesc: { fontSize: 13, color: colors.textSub, textAlign: 'center', marginVertical: space.md, lineHeight: 18 },
  confirmBtnRow: { flexDirection: 'row', gap: space.sm, width: '100%', marginTop: space.sm },
  cancelBtn: { flex: 1, backgroundColor: colors.surface, paddingVertical: 12, borderRadius: radius.md, alignItems: 'center', borderWidth: 1, borderColor: colors.border },
  cancelBtnText: { color: colors.text, fontWeight: '600' },
  okBtn: { flex: 1, backgroundColor: colors.primary, paddingVertical: 12, borderRadius: radius.md, alignItems: 'center' },
  okBtnText: { color: '#fff', fontWeight: '600' },
});