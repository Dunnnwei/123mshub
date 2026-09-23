<script setup>
import {
  ArrowUpCircle, Copy, Ellipsis, RefreshCw, SearchCheck, ShieldCheck,
} from '@lucide/vue'
import StatusBadge from './StatusBadge.vue'

const LIBRARY_SHORT = {
  github: '程序',
  skills: '共享',
  'zcode-skills': 'ZCode',
  'workbuddy-skills': 'WorkBuddy',
}

defineProps({
  skill: { type: Object, required: true },
  busyAction: { type: String, default: '' },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'copy', 'check', 'update', 'scan', 'menu', 'toggle-select', 'trust'])
</script>

<template>
  <article class="skill-row" :data-skill-key="`${skill.name}|${skill.library || ''}`" :class="{ selectable, selected }" @click="emit('select', skill)">
    <div class="skill-identity">
      <label
        v-if="selectable"
        class="row-checkbox"
        @click.stop
      >
        <input
          type="checkbox"
          :checked="selected"
          @change="emit('toggle-select', skill)"
        />
      </label>
      <button class="skill-name" type="button" @click.stop="emit('select', skill)">
        {{ skill.name }}
      </button>
      <button
        class="icon-text-button copy-inline"
        type="button"
        :title="skill.item_type === 'project' ? '复制项目使用提示' : '复制技能安装提示词'"
        @click.stop="emit('copy', skill)"
      >
        <Copy :size="14" />
        <span>复制</span>
      </button>
      <p>{{ skill.description_zh || skill.description }}</p>
      <div v-if="skill.tags?.length" class="skill-tags" aria-label="分类标签">
        <span v-for="tag in skill.tags.slice(0, 3)" :key="tag">#{{ tag }}</span>
        <span v-if="skill.tags.length > 3">+{{ skill.tags.length - 3 }}</span>
      </div>
    </div>

    <div class="skill-meta">
      <span
        class="provider-chip"
        :class="skill.provider === 'local' ? 'provider-local' : 'provider-github'"
        :title="skill.provider === 'local' ? '本地自研技能：无在线源头，版本请在编辑信息中手动维护' : 'GitHub 来源：可查版本、可在线更新'"
      >{{ skill.provider === 'local' ? '本地自研' : 'GitHub 源' }}</span>
      <span
        v-if="skill.library"
        class="library-chip"
        :class="`library-${skill.library}`"
        :title="skill.library"
      >{{ LIBRARY_SHORT[skill.library] || skill.library }}</span>
      <span class="mode-label" :class="{ 'project-label': skill.item_type === 'project' }">
        {{ skill.item_type === 'project' ? '项目' : (skill.install_mode === 'full' ? '全仓' : '标准') }}
      </span>
      <span class="version-label">{{ skill.version }}</span>
      <time v-if="skill.updated_at" class="updated-label" :datetime="skill.updated_at">{{ String(skill.updated_at).slice(0, 10) }}</time>
      <span v-if="skill.imported_from" class="import-source-label">来自 {{ skill.imported_from }}</span>
      <button v-if="skill.security_status === 'warning'" class="trust-inline-button row-trust-button" type="button" @click.stop="emit('trust', skill)">需要确认</button>
      <StatusBadge v-else :status="skill.security_status" compact />
    </div>

    <div class="row-actions" @click.stop>
      <button
        class="icon-button"
        type="button"
        :title="skill.provider === 'local' ? '本地自研技能无在线源头，版本请在编辑信息中手动维护' : '查版本'"
        :disabled="!!busyAction || skill.provider === 'local'"
        @click="emit('check', skill)"
      >
        <SearchCheck :size="17" />
      </button>
      <button
        class="icon-button"
        type="button"
        :title="skill.provider === 'local' ? '本地自研技能无在线源头，版本请在编辑信息中手动维护' : '更新'"
        :disabled="!!busyAction || skill.provider === 'local'"
        @click="emit('update', skill)"
      >
        <RefreshCw :size="17" :class="{ spinning: busyAction === 'update' }" />
      </button>
      <button class="icon-button" type="button" title="安全检查" :disabled="!!busyAction" @click="emit('scan', skill)">
        <ShieldCheck :size="17" />
      </button>
      <button
        v-if="skill.item_type !== 'project'"
        class="icon-button action-mode"
        type="button"
        :title="skill.install_mode === 'full' ? '降级为标准安装' : '升级为全仓安装'"
        :disabled="!!busyAction"
        @click="emit('menu', skill)"
      >
        <ArrowUpCircle :size="17" :class="{ 'rotate-down': skill.install_mode === 'full' }" />
      </button>
      <button class="icon-button action-more" type="button" title="查看详情" @click="emit('select', skill)">
        <Ellipsis :size="18" />
      </button>
    </div>
  </article>
</template>
