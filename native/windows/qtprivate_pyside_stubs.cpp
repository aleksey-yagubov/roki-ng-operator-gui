// Stubs for Qt private symbols that are not exported by the Qt build bundled
// with PySide6 (the official qt.io binaries export them; the wheel build does
// not). These symbols are only referenced through inline code paths in
// private headers; the bodies below are intentionally conservative and are
// not expected to run during docking operations.
//
// Part of the Windows port of ROKI NG Operator; not used on Linux/macOS.

#include <QtCore/qglobal.h>
#include <QtCore/qloggingcategory.h>

#include <QtCore/private/qproperty_p.h>

#include <QtQml/private/qqmldata_p.h>
#include <QtQml/private/qqmlimport_p.h>
#include <QtQml/private/qqmlthread_p.h>
#include <QtQml/private/qqmlpropertycache_p.h>
#include <QtQml/private/qv4persistent_p.h>
#include <QtQml/private/qv4stacklimits_p.h>
#include <QtQml/private/qv4compileddata_p.h>
#include <QtQml/private/qv4mm_p.h>
#include <QtQml/private/qv4sparsearray_p.h>
#include <QtQml/private/qv4functionobject_p.h>

#include <QtQuick/private/qquickitem_p.h>

namespace {

[[noreturn]] void rokiUnreachable(const char *what)
{
    qFatal("Qt private stub called: %s", what);
}

}

void QPropertyObserverPointer::evaluateBindings(PendingBindingObserverList &bindingObservers,
                                                QBindingStatus *status)
{
    // Binding evaluation through this inline path is not expected for the
    // docking frontend; Qt's own binding engine lives inside Qt6Core.
    Q_UNUSED(bindingObservers);
    Q_UNUSED(status);
}

QtPrivate::BindingEvaluationState::BindingEvaluationState(QPropertyBindingPrivate *b,
                                                          QBindingStatus *status)
{
    Q_UNUSED(status);
    binding = b;
    previousState = nullptr;
    currentState = nullptr;
}

void QQmlData::NotifyList::layout()
{
    // Notify lists are laid out by QtQuick/QQml internals inside Qt6Qml; the
    // docking frontend never fires QML property notifications itself.
}

const QLoggingCategory &lcQmlImport()
{
    static const QLoggingCategory category("qt.qml.import");
    return category;
}

bool QQmlThread::isThisThread() const
{
    return true;
}

bool QQmlThread::isRunning() const
{
    return true;
}

OverrideSemantics::Status OverrideSemantics::handleOverride(QQmlPropertyData &overridingProperty,
                                                            QQmlPropertyData *existingProperty,
                                                            CheckMode mode)
{
    Q_UNUSED(overridingProperty);
    Q_UNUSED(existingProperty);
    Q_UNUSED(mode);
    return OverrideSemantics::Status::Valid;
}

QV4::PersistentValueStorage::Iterator::Iterator(void *p, int idx)
    : p(p)
    , index(idx)
{
}

QV4::StackProperties QV4::stackProperties()
{
    return StackProperties{};
}

QQmlType QV4::CompiledData::CompilationUnit::qmlTypeForComponent(const QString &inlineComponentName) const
{
    Q_UNUSED(inlineComponentName);
    return QQmlType();
}

QV4::HeapItem *QV4::BlockAllocator::allocate(size_t size, bool forceAllocation)
{
    Q_UNUSED(size);
    Q_UNUSED(forceAllocation);
    return nullptr;
}

QV4::HeapItem *QV4::HugeItemAllocator::allocate(size_t size)
{
    Q_UNUSED(size);
    return nullptr;
}

const QV4::SparseArrayNode *QV4::SparseArrayNode::nextNode() const
{
    return nullptr;
}

// VTable data symbols (used by QV4::FunctionObject::isBoundFunction()). A
// zeroed vtable is never equal to a live object's vtable, so bound-function
// checks simply return false.
const QV4::VTable QV4::BoundFunction::static_vtbl = {};
const QV4::VTable QV4::BoundConstructor::static_vtbl = {};

QQuickItemKeyFilter::~QQuickItemKeyFilter() = default;

void QQuickItemKeyFilter::keyPressed(QKeyEvent *event, bool post)
{
    Q_UNUSED(event);
    Q_UNUSED(post);
}

void QQuickItemKeyFilter::keyReleased(QKeyEvent *event, bool post)
{
    Q_UNUSED(event);
    Q_UNUSED(post);
}

void QQuickItemKeyFilter::inputMethodEvent(QInputMethodEvent *event, bool post)
{
    Q_UNUSED(event);
    Q_UNUSED(post);
}

QVariant QQuickItemKeyFilter::inputMethodQuery(Qt::InputMethodQuery query) const
{
    Q_UNUSED(query);
    return QVariant();
}

void QQuickItemKeyFilter::shortcutOverrideEvent(QKeyEvent *event)
{
    Q_UNUSED(event);
}

void QQuickItemKeyFilter::componentComplete()
{
}
