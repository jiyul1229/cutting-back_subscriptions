from fastapi import APIRouter

from app.schemas import ServicePreset

router = APIRouter(prefix="/api/presets", tags=["presets"])

# 구독 등록 화면에서 이름·기본 요금을 미리 채우는 주요 서비스(문서 R1 대응, 할 일 #1).
# 요금은 대표 요금제의 참고값입니다. 서비스가 요금을 바꿀 수 있으므로 등록 화면에서 사용자가 고칩니다.
# Figma 시안에 나온 서비스는 시안 금액을 씁니다. android_package는 Play 스토어 주소의 id= 값이며 자동 측정 연결에 씁니다.
PRESETS = [
    ServicePreset(name="넷플릭스", plan_name="프리미엄", price_won=17000, billing_cycle="monthly",
                  category="ott", android_package="com.netflix.mediaclient"),
    ServicePreset(name="유튜브 프리미엄", plan_name="개인", price_won=14900, billing_cycle="monthly",
                  category="ott", android_package="com.google.android.youtube"),
    ServicePreset(name="티빙", plan_name="스탠다드", price_won=13500, billing_cycle="monthly",
                  category="ott", android_package="net.cj.cjhv.gs.tving"),
    ServicePreset(name="디즈니+", plan_name="스탠다드", price_won=9900, billing_cycle="monthly",
                  category="ott", android_package="com.disney.disneyplus"),
    ServicePreset(name="쿠팡 와우", plan_name="와우 멤버십", price_won=7890, billing_cycle="monthly",
                  category="shopping", android_package="com.coupang.mobile.play"),
    ServicePreset(name="네이버플러스 멤버십", plan_name=None, price_won=4900, billing_cycle="monthly",
                  category="shopping", android_package=None),
    ServicePreset(name="멜론", plan_name="스트리밍 클럽", price_won=10900, billing_cycle="monthly",
                  category="lifestyle", android_package="com.iloen.melon"),
    ServicePreset(name="스포티파이", plan_name="프리미엄 개인", price_won=11990, billing_cycle="monthly",
                  category="lifestyle", android_package="com.spotify.music"),
    ServicePreset(name="리디셀렉트", plan_name=None, price_won=9900, billing_cycle="monthly",
                  category="book", android_package="com.initialcoms.ridi"),
    ServicePreset(name="밀리의서재", plan_name=None, price_won=9900, billing_cycle="monthly",
                  category="book", android_package="kr.co.millie.millieapp"),
]


@router.get("", response_model=list[ServicePreset])
def list_presets():
    return PRESETS
