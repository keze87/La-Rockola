import { reactive, nextTick } from 'vue';

const ctxMenu = reactive({
    visible: false,
    x: 0,
    y: 0,
    track: null,
    source: 'library', // 'library', 'queue', 'history'
    index: null,
});

export function useContextMenu() {
    function openCtxMenu(event, track, source = 'library', index = null) {
        const margin = 12;
        let x = event.clientX || (event.touches && event.touches[0].clientX) || 0;
        let y = event.clientY || (event.touches && event.touches[0].clientY) || 0;

        ctxMenu.visible = true;
        ctxMenu.track = track;
        ctxMenu.source = source;
        ctxMenu.index = index;
        ctxMenu.x = x;
        ctxMenu.y = y;

        // Adjust position so it doesn't render off-screen
        nextTick(() => {
            const menu = document.querySelector('.ctx-menu');
            if (menu) {
                const w = menu.offsetWidth;
                const h = menu.offsetHeight;
                const winW = window.innerWidth || document.documentElement.clientWidth;
                const winH = window.innerHeight || document.documentElement.clientHeight;

                if (x + w + margin > winW) x = winW - w - margin;
                if (y + h + margin > winH) y = winH - h - margin;
                if (x < margin) x = margin;
                if (y < margin) y = margin;

                ctxMenu.x = x;
                ctxMenu.y = y;
            }
        });
    }

    function closeCtxMenu() {
        ctxMenu.visible = false;
    }

    return {
        closeCtxMenu,
        ctxMenu,
        openCtxMenu,
    };
}
