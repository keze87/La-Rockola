import { h, markRaw, type VNode } from 'vue';
import { toast } from 'vue-sonner';

type ToastMessage = string | { prefix?: string; highlight: string; suffix?: string };
type ToastType = 'info' | 'success' | 'warning' | 'error';

// `msg` is either a plain string, or `{ prefix, highlight, suffix }` when a
// track title needs to be shown in bold. For the latter we hand vue-sonner
// a tiny Vue component built with h() instead of an HTML string — h()
// treats `highlight` as a text node (auto-escaped, just like `{{ }}` in a
// template), so a track title full of angle brackets can never be
// interpreted as markup. Track titles can come from untrusted sources
// (pasted URLs, file metadata), so this can't be a string-concat + v-html
// like the old implementation was.
function toastContent(msg: ToastMessage): string | VNode {
	if (typeof msg === 'string') return msg;

	if (!msg.highlight) return `${msg.prefix || ''}${msg.suffix || ''}`;

	return markRaw({
		setup() {
			return () => h('span', [msg.prefix || '', h('b', msg.highlight), msg.suffix || '']);
		},
	}) as unknown as VNode;
}

export function useToasts() {
	function showToast(msg: ToastMessage, type: ToastType = 'info') {
		const content = toastContent(msg);

		if (type === 'success') toast.success(content);
		else if (type === 'warning') toast.warning(content);
		else if (type === 'error') toast.error(content);
		else toast(content);
	}

	return { showToast };
}
