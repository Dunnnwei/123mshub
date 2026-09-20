<script setup>
import { computed } from 'vue'
import { AlertTriangle, CheckCircle2, ShieldCheck } from '@lucide/vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({
  skills: { type: Array, required: true },
})
const emit = defineEmits(['scan', 'select', 'trust'])

const warnings = computed(() => props.skills.filter((skill) => skill.security_status === 'warning'))
const unchecked = computed(() => props.skills.filter((skill) => skill.security_status === 'unchecked'))
const safe = computed(() => props.skills.filter((skill) => skill.security_status === 'safe'))
</script>

<template>
  <section class="security-view">
    <header class="view-heading security-heading">
      <div>
        <h1>安全中心</h1>
        <p>风险审查在技能进入 agent 目录之前完成。</p>
      </div>
      <div class="security-metrics">
        <span><strong>{{ safe.length }}</strong> 安全</span>
        <span><strong>{{ warnings.length }}</strong> 待确认</span>
        <span><strong>{{ unchecked.length }}</strong> 未检查</span>
      </div>
    </header>

    <div v-if="warnings.length" class="security-section">
      <div class="security-section-title warning-title">
        <AlertTriangle :size="19" />
        <div><h2>需要确认</h2><p>规则扫描发现危险行为或可疑指令，请查看具体文件。</p></div>
      </div>
      <article v-for="skill in warnings" :key="skill.name" class="security-row" @click="emit('select', skill)">
        <div>
          <strong>{{ skill.name }}</strong>
          <p>{{ skill.security_findings.length }} 项发现 · {{ skill.security_route === 'ai' ? 'AI 深度审查' : (skill.security_route === 'trust' ? '已人工信任' : '离线规则检查') }}</p>
        </div>
        <StatusBadge :status="skill.security_status" />
        <div class="security-row-actions" @click.stop>
          <button class="secondary-button" type="button" @click="emit('scan', skill)">
            重新检查
          </button>
          <button class="trust-button" type="button" @click="emit('trust', skill)">
            信任
          </button>
        </div>
      </article>
    </div>

    <div v-if="unchecked.length" class="security-section">
      <div class="security-section-title">
        <ShieldCheck :size="19" />
        <div><h2>尚未检查</h2><p>建议在复制给 agent 之前完成至少一次路线 A 检查。</p></div>
      </div>
      <article v-for="skill in unchecked" :key="skill.name" class="security-row" @click="emit('select', skill)">
        <div><strong>{{ skill.name }}</strong><p>{{ skill.description }}</p></div>
        <StatusBadge :status="skill.security_status" />
        <button class="secondary-button" type="button" @click.stop="emit('scan', skill)">开始检查</button>
      </article>
    </div>

    <div v-if="!warnings.length && !unchecked.length" class="security-clean">
      <CheckCircle2 :size="27" />
      <h2>{{ skills.length ? '所有技能均已通过检查' : '还没有需要检查的技能' }}</h2>
      <p>{{ skills.length ? '当前仓库没有未处理的安全问题。' : '技能入库时会自动执行路线 A 离线检查。' }}</p>
    </div>
  </section>
</template>
