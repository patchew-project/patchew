% include('templates/header.tpl', title='Series')

<style type="text/css">
.message-toggler {
    cursor: pointer;
}
.message .panel-body {
    padding-top: 5px;
    padding-bottom: 5px;
}
.panel-body .body-full {
    background-color: #fff;
    border: none;
    padding: 5px;
    display: none;
}
.message {
    margin-bottom: 5px;
}
.message-preview {
    display: block;
    color: #555;
    text-overflow: ellipsis;
    overflow: hidden;
    white-space: nowrap;
}

.reply-lvl-0 {
}
.reply-lvl-1 {
    margin-left: 8px;
}
.reply-lvl-2 {
    margin-left: 16px;
}
.reply-lvl-3 {
    margin-left: 24px;
}
.reply-lvl-4 {
    margin-left: 32px;
}
</style>

%def put_message(msg, lvl):
    <div class="panel panel-default message reply-lvl-{{min(lvl, 5)}}">
        <div class="panel-heading message-toggler">
            <h3 class="panel-title">
            {{msg['visible-subject']}}
            <span class="pull-right">
                <small>Posted by</small>
                <span class="message-author" title="{{msg['author-address']}}">{{msg['author']}}</span>
                <small>at</small>
                <span class="timestamp" title="{{msg['date']}}">{{msg['age']}}</span>
                <small>ago</small>
            </span>
            </h3>
        </div>
        <div class="panel-body">
            <span class="message-preview message-toggler message-toggle">{{msg['preview']}} ...</span>
            <pre class="body-full message-toggle">{{msg['body']}}</pre>
        </div>
    </div>
        %for m in msg['replies']:
            %put_message(m, lvl + 1)
        %end
%end

%put_message(thread, 0)

<script language="javascript" type="text/javascript">

function main() {
    $(".message-toggler").click(function () {
        $(this).parent().find(".message-toggle").toggle();
    });
    $(".timestamp").each(function (i, o) {
        $(o).attr("title", new Date(1000 * $(o).attr("title")));
    });
}

$(main);

</script>
% include('templates/footer.tpl')
