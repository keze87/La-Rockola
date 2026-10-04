import { h, markRaw, type VNode } from 'vue';
import { toast } from 'vue-sonner';

type ToastMessage = string | { prefix?: string; highlight: string; suffix?: string };
type ToastType = 'info' | 'success' | 'warning' | 'error';

// `msg` es un string común o `{ prefix, highlight, suffix }` cuando el título
// del tema tiene que verse en negrita. En este último caso le pasamos a vue-sonner
// un mini componente Vue armado con h() en lugar de un string HTML: h()
// trata `highlight` como nodo de texto (escapado automático como `{{ }}` en templates),
// evitando inyección de markup si el título contiene caracteres raros. Al provenir
// de fuentes externas (URLs pegadas, metadatos de archivos), no podemos concatenar strings con v-html.
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
